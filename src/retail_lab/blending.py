"""モデルの混ぜ方と、出荷前の後処理。"""

from __future__ import annotations

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


def fit_log_weights_by_horizon(
    pred_map: dict[str, pd.DataFrame], actual: pd.DataFrame, origin: pd.Timestamp
) -> dict[int, dict[str, float]]:
    """予測日ごとに非負最小二乗の重みを当てる。再帰は後半で誤差が溜まりやすい。"""
    truth = actual[[ROW_ID, DATE, TARGET]].copy()
    truth["horizon"] = (pd.to_datetime(truth[DATE]) - origin).dt.days
    weights: dict[int, dict[str, float]] = {}
    for _step, part in truth.groupby("horizon"):
        subset = {name: frame[frame[ROW_ID].isin(part[ROW_ID])] for name, frame in pred_map.items()}
        if part.empty:
            continue
        horizon_key = int(part["horizon"].to_numpy()[0])
        weights[horizon_key] = fit_log_weights(subset, part)
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
    last = history[DATE].max()
    window = history[history[DATE] > last - pd.Timedelta(days=lookback)]
    totals = window.groupby(SERIES_ID)[TARGET].sum()
    dead = set(totals[totals <= 0].index)
    out = pred.copy()
    out.loc[out[SERIES_ID].isin(dead), PRED] = 0.0
    return out
