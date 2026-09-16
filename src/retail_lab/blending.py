"""モデルの混ぜ方と、出荷前の後処理。"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from retail_lab import DATE, ROW_ID, SERIES_ID, TARGET
from retail_lab.metrics import business_metrics, rmsle

PRED = "pred"


def inverse_rmsle_weights(scores: dict[str, float]) -> dict[str, float]:
    """検証 RMSLE の逆数を重みにする。悪いモデルは自動的に薄くなる。"""
    usable = {k: v for k, v in scores.items() if np.isfinite(v) and v > 0}
    if not usable:
        return {}
    inverse = {k: 1.0 / v for k, v in usable.items()}
    total = sum(inverse.values())
    return {k: float(v / total) for k, v in inverse.items()}


def fit_log_weights(pred_map: dict[str, pd.DataFrame], actual: pd.DataFrame) -> dict[str, float]:
    """検証窓で RMSLE を最小にする非負の重みを当てる。

    RMSLE は log1p 空間での二乗誤差なので、その空間での非負最小二乗がそのまま
    最適な混ぜ方になる。推定するのはモデル数（数個）だけで、観測は検証窓の全行
    （公式データなら28,512行）なので、過学習の心配はほぼない。
    """
    from scipy.optimize import nnls

    names = sorted(pred_map)
    truth = actual[[ROW_ID, TARGET]].sort_values(ROW_ID)
    columns = []
    for name in names:
        frame = pred_map[name][[ROW_ID, PRED]].set_index(ROW_ID).loc[truth[ROW_ID]]
        columns.append(np.log1p(frame[PRED].clip(lower=0).to_numpy()))
    matrix = np.column_stack(columns)
    target = np.log1p(truth[TARGET].clip(lower=0).to_numpy())

    coefficients, _residual = nnls(matrix, target)
    if float(coefficients.sum()) <= 0:
        return inverse_rmsle_weights({name: 1.0 for name in names})
    # 正規化はしない。合計1に押し込むと、当てはめた最適点からずれてしまう。
    return {name: float(w) for name, w in zip(names, coefficients, strict=True) if w > 0}


def prediction_origin(pred_map: dict[str, pd.DataFrame]) -> pd.Timestamp:
    """予測の1日目の前日。検証窓と提出窓で日付が違っても、horizon=1 が揃う。"""
    first = min(pd.to_datetime(frame[DATE]).min() for frame in pred_map.values())
    return pd.Timestamp(first) - pd.Timedelta(days=1)


def _family_of(frame: pd.DataFrame) -> pd.Series:
    if "family" in frame.columns:
        return frame["family"].astype(str)
    if SERIES_ID in frame.columns:
        return frame[SERIES_ID].astype(str).str.split("::").str[-1]
    return pd.Series(["all"] * len(frame), index=frame.index)


def fit_log_weights_by_horizon(
    pred_map: dict[str, pd.DataFrame], actual: pd.DataFrame, origin: pd.Timestamp
) -> dict[int, dict[str, float]]:
    """予測日ごとに非負最小二乗の重みを当てる。再帰は後半で誤差が溜まりやすい。"""
    truth = actual[[ROW_ID, DATE, TARGET]].copy()
    truth["horizon"] = (pd.to_datetime(truth[DATE]) - origin).dt.days
    weights: dict[int, dict[str, float]] = {}
    for _step, part in truth.groupby("horizon"):
        if part.empty:
            continue
        subset = {name: frame[frame[ROW_ID].isin(part[ROW_ID])] for name, frame in pred_map.items()}
        horizon_key = int(part["horizon"].to_numpy()[0])
        weights[horizon_key] = fit_log_weights(subset, part)
    return weights


def fit_log_weights_by_family(
    pred_map: dict[str, pd.DataFrame], actual: pd.DataFrame
) -> dict[str, dict[str, float]]:
    """商品ファミリーごとに非負最小二乗の重みを当てる。当たり方が系統で違うため。"""
    truth = actual[[ROW_ID, TARGET]].copy()
    sample = next(iter(pred_map.values()))
    families = pd.Series(_family_of(sample).to_numpy(), index=sample[ROW_ID].to_numpy())
    truth["family"] = truth[ROW_ID].map(families)
    weights: dict[str, dict[str, float]] = {}
    for family, part in truth.groupby("family"):
        if part.empty or pd.isna(family):
            continue
        subset = {name: frame[frame[ROW_ID].isin(part[ROW_ID])] for name, frame in pred_map.items()}
        weights[str(family)] = fit_log_weights(subset, part)
    return weights


def blend_by_horizon(
    pred_map: dict[str, pd.DataFrame],
    weights_by_horizon: dict[int, dict[str, float]],
    origin: pd.Timestamp,
) -> pd.DataFrame:
    """日ごとの重みで混ぜる。重みがない日は全モデル均等に近づけるため空なら落とす。"""
    pieces: list[pd.DataFrame] = []
    sample = next(iter(pred_map.values()))
    horizons = (pd.to_datetime(sample[DATE]) - origin).dt.days
    for step, weights in weights_by_horizon.items():
        row_ids = sample.loc[horizons == step, ROW_ID]
        subset = {name: frame[frame[ROW_ID].isin(row_ids)] for name, frame in pred_map.items()}
        if not row_ids.empty:
            pieces.append(blend(subset, weights))
    if not pieces:
        raise ValueError("日ごとの混合を作れる行がありません")
    return pd.concat(pieces, ignore_index=True)


def blend_by_family(
    pred_map: dict[str, pd.DataFrame],
    weights_by_family: dict[str, dict[str, float]],
) -> pd.DataFrame:
    """ファミリーごとの重みで混ぜる。"""
    pieces: list[pd.DataFrame] = []
    sample = next(iter(pred_map.values())).copy()
    sample["_family"] = _family_of(sample)
    for family, weights in weights_by_family.items():
        row_ids = sample.loc[sample["_family"] == family, ROW_ID]
        subset = {name: frame[frame[ROW_ID].isin(row_ids)] for name, frame in pred_map.items()}
        if not row_ids.empty:
            pieces.append(blend(subset, weights))
    if not pieces:
        raise ValueError("ファミリーごとの混合を作れる行がありません")
    return pd.concat(pieces, ignore_index=True)


def choose_blend(
    val_preds: dict[str, pd.DataFrame],
    test_preds: dict[str, pd.DataFrame],
    train: pd.DataFrame,
    val: pd.DataFrame,
    labeled: pd.DataFrame,
    windows: tuple[int, ...] = (0, 3, 7, 14, 21),
) -> dict[str, Any]:
    """検証窓で混ぜ方とゼロ窓を選ぶ。日別重みも候補に入れる。"""
    scores = {name: score_against(frame, val) for name, frame in val_preds.items()}
    best_single = min(scores, key=lambda name: scores[name])
    origin_val = prediction_origin(val_preds)
    origin_test = prediction_origin(test_preds)
    horizon_weights = fit_log_weights_by_horizon(val_preds, val, origin_val)
    family_weights = fit_log_weights_by_family(val_preds, val)
    mean_horizon = {
        name: float(np.mean([part.get(name, 0.0) for part in horizon_weights.values()] or [0.0]))
        for name in val_preds
    }
    mean_family = {
        name: float(np.mean([part.get(name, 0.0) for part in family_weights.values()] or [0.0]))
        for name in val_preds
    }
    options: dict[str, tuple[pd.DataFrame, pd.DataFrame, dict[str, float]]] = {
        "rule": (
            blend(val_preds, inverse_rmsle_weights(scores)),
            blend(test_preds, inverse_rmsle_weights(scores)),
            inverse_rmsle_weights(scores),
        ),
        "fitted": (
            blend(val_preds, fit_log_weights(val_preds, val)),
            blend(test_preds, fit_log_weights(val_preds, val)),
            fit_log_weights(val_preds, val),
        ),
        "single": (
            blend(val_preds, {best_single: 1.0}),
            blend(test_preds, {best_single: 1.0}),
            {best_single: 1.0},
        ),
        "fitted_horizon": (
            blend_by_horizon(val_preds, horizon_weights, origin_val),
            blend_by_horizon(test_preds, horizon_weights, origin_test),
            mean_horizon,
        ),
        "fitted_family": (
            blend_by_family(val_preds, family_weights),
            blend_by_family(test_preds, family_weights),
            mean_family,
        ),
    }

    best_score = float("inf")
    chosen: dict[str, Any] | None = None
    per_strategy: dict[str, float] = {}
    for name, (val_raw, test_raw, weights) in options.items():
        for window in windows:
            val_candidate = zero_out_dead_series(train, val_raw, window) if window else val_raw
            score = score_against(val_candidate, val)
            per_strategy[name] = min(per_strategy.get(name, float("inf")), score)
            if score < best_score:
                best_score = score
                test_candidate = (
                    zero_out_dead_series(labeled, test_raw, window) if window else test_raw
                )
                chosen = {
                    "strategy": name,
                    "zero_window": window,
                    "val": val_candidate,
                    "test": test_candidate,
                    "weights": weights,
                    "weights_by_horizon": horizon_weights if name == "fitted_horizon" else None,
                    "weights_by_family": family_weights if name == "fitted_family" else None,
                    "best_single": best_single,
                }
    if chosen is None:
        raise ValueError("混合候補がありません")
    chosen["score"] = best_score
    chosen["candidates"] = per_strategy
    chosen["model_scores"] = scores
    return chosen


def blend(
    pred_map: dict[str, pd.DataFrame], weights: dict[str, float], space: str = "log"
) -> pd.DataFrame:
    """重み付き平均。指標が log なので既定も log 空間で混ぜる。"""
    base: pd.DataFrame | None = None
    acc: np.ndarray | None = None
    order: np.ndarray | None = None
    for name, weight in weights.items():
        frame = pred_map[name].sort_values(ROW_ID)
        if base is None or acc is None or order is None:
            base = frame.drop(columns=[PRED]).copy()
            acc = np.zeros(len(frame), dtype=np.float64)
            order = frame[ROW_ID].to_numpy()
        values = frame.set_index(ROW_ID).loc[order, PRED].clip(lower=0).to_numpy()
        acc = acc + weight * (np.log1p(values) if space == "log" else values)
    if base is None or acc is None:
        raise ValueError("混ぜるモデルがありません")
    out = base
    out[PRED] = np.clip(np.expm1(acc) if space == "log" else acc, 0, None)
    return out


def score_against(pred: pd.DataFrame, actual: pd.DataFrame) -> float:
    merged = pred.merge(actual[[ROW_ID, TARGET]], on=ROW_ID, how="inner")
    return rmsle(merged[TARGET], merged[PRED])


def grouped_rmsle(
    pred: pd.DataFrame, actual: pd.DataFrame, group: str, *, worst: int = 12
) -> list[dict[str, float | int | str]]:
    """検証誤差が大きいグループから順に返す。次に直す場所を決めるため。"""
    columns = [ROW_ID, TARGET]
    if group not in actual.columns:
        return []
    if group != ROW_ID:
        columns.append(group)
    merged = pred.merge(actual[columns], on=ROW_ID, how="inner")
    rows: list[dict[str, float | int | str]] = []
    for key, part in merged.groupby(group, sort=False):
        rows.append(
            {
                "group": str(key),
                "rmsle": round(float(rmsle(part[TARGET], part[PRED])), 5),
                "n": int(len(part)),
            }
        )
    rows.sort(key=lambda item: -float(item["rmsle"]))
    return rows[:worst]


def business_against(pred: pd.DataFrame, actual: pd.DataFrame) -> dict[str, float]:
    merged = pred.merge(actual[[ROW_ID, TARGET]], on=ROW_ID, how="inner")
    return business_metrics(merged[TARGET], merged[PRED])


def zero_out_dead_series(
    history: pd.DataFrame, pred: pd.DataFrame, lookback: int = 21
) -> pd.DataFrame:
    """直近 lookback 日がすべて0の系列は、扱いを止めたものとみなして0を出す。"""
    if lookback <= 0 or SERIES_ID not in history.columns or TARGET not in history.columns:
        return pred
    last = history[DATE].max()
    window = history[history[DATE] > last - pd.Timedelta(days=lookback)]
    totals = window.groupby(SERIES_ID)[TARGET].sum()
    dead = set(totals[totals <= 0].index)
    out = pred.copy()
    out.loc[out[SERIES_ID].isin(dead), PRED] = 0.0
    return out
