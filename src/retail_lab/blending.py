"""モデルの混ぜ方と、出荷前の後処理。"""

from __future__ import annotations

from collections.abc import Sequence
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


def pool_predictions(
    pred_map: dict[str, pd.DataFrame],
    names: Sequence[str] | None = None,
    *,
    how: str = "min",
) -> pd.DataFrame:
    """複数モデルの予測を行ごとにまとめる。過大予測が多い系統の抑え込み用。"""
    usable = [name for name in (names or sorted(pred_map)) if name in pred_map]
    if len(usable) < 2:
        raise ValueError("まとめるモデルが足りません")
    if how not in {"min", "median", "mean", "gmean"}:
        raise ValueError(f"未対応のまとめ方です: {how}")
    base = pred_map[usable[0]][[ROW_ID, DATE, SERIES_ID]].copy()
    order = base[ROW_ID].to_numpy()
    matrix = np.column_stack(
        [
            pred_map[name].set_index(ROW_ID).loc[order, PRED].clip(lower=0).to_numpy()
            for name in usable
        ]
    )
    if how == "min":
        values = matrix.min(axis=1)
    elif how == "median":
        values = np.median(matrix, axis=1)
    elif how == "mean":
        values = matrix.mean(axis=1)
    else:
        values = np.expm1(np.mean(np.log1p(matrix), axis=1))
    out = base
    out[PRED] = np.clip(values, 0, None)
    return out


def with_pooled_candidates(
    val_preds: dict[str, pd.DataFrame],
    test_preds: dict[str, pd.DataFrame],
) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
    """過大予測を抑える行ごとのまとめを候補へ足す。"""
    pool_names = [
        name
        for name in (
            "direct_horizon_lgbm",
            "direct_hurdle",
            "direct_family_trend_hurdle",
            "recursive_lgbm",
            "recursive_hurdle_deep",
            "recursive_family_trend",
            "recursive_family_trend_hurdle",
            "recursive_lgbm_no_eq",
            "timesfm",
        )
        if name in val_preds and name in test_preds
    ]
    if len(pool_names) < 2:
        return val_preds, test_preds
    val_out = dict(val_preds)
    test_out = dict(test_preds)
    for stale in ("robust_min", "robust_median", "robust_gmean"):
        val_out.pop(stale, None)
        test_out.pop(stale, None)
    for how, key in (("min", "robust_min"), ("median", "robust_median"), ("gmean", "robust_gmean")):
        val_out[key] = pool_predictions(val_preds, pool_names, how=how)
        test_out[key] = pool_predictions(test_preds, pool_names, how=how)
    return val_out, test_out


def shrink_weights(
    group_weights: dict[str, dict[str, float]],
    global_weights: dict[str, float],
    alpha: float,
) -> dict[str, dict[str, float]]:
    """グループ別の重みを全体の重みへ寄せる。少数行のグループの当てはめ過ぎを抑える。"""
    names = sorted({*global_weights, *(n for part in group_weights.values() for n in part)})
    shrunk: dict[str, dict[str, float]] = {}
    for group, weights in group_weights.items():
        mixed = {
            name: alpha * weights.get(name, 0.0) + (1.0 - alpha) * global_weights.get(name, 0.0)
            for name in names
        }
        positive = {name: value for name, value in mixed.items() if value > 0}
        shrunk[group] = positive or dict(global_weights)
    return shrunk


def series_halves(pred_map: dict[str, pd.DataFrame]) -> tuple[set[Any], set[Any]]:
    """系列を2つに割る。ファミリーごとに1つ飛ばしで分けるので、両側に全ファミリーが残る。

    分けられないとき（系列が少ない、ファミリーが片側にしかない）は空を返す。
    呼び出し側はそれを「隠して採点できない」合図として扱う。
    """
    sample = next(iter(pred_map.values()))
    if SERIES_ID not in sample.columns:
        return set(), set()
    frame = sample[[ROW_ID, SERIES_ID]].copy()
    frame["_family"] = _family_of(sample).to_numpy()
    left: set[str] = set()
    for _family, part in frame.groupby("_family"):
        series = sorted(part[SERIES_ID].astype(str).unique())
        if len(series) < 2:
            return set(), set()
        left.update(series[0::2])
    fit_mask = frame[SERIES_ID].astype(str).isin(left)
    fit_ids = set(frame.loc[fit_mask, ROW_ID])
    hold_ids = set(frame.loc[~fit_mask, ROW_ID])
    if not fit_ids or not hold_ids:
        return set(), set()
    return fit_ids, hold_ids


def _subset(pred_map: dict[str, pd.DataFrame], row_ids: set[Any]) -> dict[str, pd.DataFrame]:
    return {name: frame[frame[ROW_ID].isin(row_ids)] for name, frame in pred_map.items()}


def snap_small_to_zero(pred: pd.DataFrame, threshold: float) -> pd.DataFrame:
    """小さすぎる予測を0にする。売れない日が多い系統では、迷ったら0の方が罰が軽い。

    系列ごとの打ち切り（zero_out_dead_series）とは別物で、こちらは1行ずつ見る。
    """
    if threshold <= 0:
        return pred
    out = pred.copy()
    out.loc[out[PRED] < threshold, PRED] = 0.0
    return out


def fit_family_log_scales(
    pred: pd.DataFrame, actual: pd.DataFrame, *, shrink: float = 1.0
) -> dict[str, float]:
    """売り場ごとに log1p 予測の倍率を当てる。1 なら補正なし。

    LINGERIE のように売れた日を小さく見がちな系統を、見ていない店で測って持ち上げる。
    """
    sample = pred.copy()
    sample["_family"] = _family_of(sample)
    merged = sample.merge(actual[[ROW_ID, TARGET]], on=ROW_ID, how="inner")
    scales: dict[str, float] = {}
    for family, part in merged.groupby("_family"):
        if part.empty or pd.isna(family):
            continue
        log_pred = np.log1p(part[PRED].clip(lower=0).to_numpy())
        log_actual = np.log1p(part[TARGET].clip(lower=0).to_numpy())
        denom = float(np.dot(log_pred, log_pred))
        if denom <= 1e-12:
            scales[str(family)] = 1.0
            continue
        raw = float(np.dot(log_pred, log_actual) / denom)
        raw = float(np.clip(raw, 0.5, 1.5))
        scales[str(family)] = shrink * raw + (1.0 - shrink) * 1.0
    return scales


def apply_family_log_scales(pred: pd.DataFrame, scales: dict[str, float]) -> pd.DataFrame:
    if not scales:
        return pred
    out = pred.copy()
    families = _family_of(out)
    scaled = out[PRED].to_numpy(dtype=float).copy()
    for family, scale in scales.items():
        if abs(scale - 1.0) < 1e-12:
            continue
        mask = families.to_numpy() == family
        scaled[mask] = np.expm1(np.log1p(np.clip(scaled[mask], 0, None)) * scale)
    out[PRED] = np.clip(scaled, 0, None)
    return out


def _fit_plan(
    strategy: str,
    pred_map: dict[str, pd.DataFrame],
    actual: pd.DataFrame,
    alpha: float = 1.0,
) -> dict[str, Any]:
    """混ぜ方を1つ当てはめる。適用に必要なものだけ返す。"""
    if strategy == "rule":
        scores = {name: score_against(frame, actual) for name, frame in pred_map.items()}
        return {"kind": "flat", "weights": inverse_rmsle_weights(scores)}
    if strategy == "fitted":
        return {"kind": "flat", "weights": fit_log_weights(pred_map, actual)}
    if strategy == "single":
        scores = {name: score_against(frame, actual) for name, frame in pred_map.items()}
        best = min(scores, key=lambda name: scores[name])
        return {"kind": "flat", "weights": {best: 1.0}}
    if strategy == "fitted_horizon":
        return {
            "kind": "horizon",
            "by_horizon": fit_log_weights_by_horizon(pred_map, actual, prediction_origin(pred_map)),
        }
    if strategy == "fitted_family":
        by_family = fit_log_weights_by_family(pred_map, actual)
        if alpha < 1.0:
            by_family = shrink_weights(by_family, fit_log_weights(pred_map, actual), alpha)
        return {"kind": "family", "by_family": by_family, "alpha": alpha}
    raise ValueError(f"未対応の混ぜ方です: {strategy}")


def _apply_plan(plan: dict[str, Any], pred_map: dict[str, pd.DataFrame]) -> pd.DataFrame:
    if plan["kind"] == "flat":
        return blend(pred_map, plan["weights"])
    if plan["kind"] == "horizon":
        return blend_by_horizon(pred_map, plan["by_horizon"], prediction_origin(pred_map))
    return blend_by_family(pred_map, plan["by_family"])


def _mean_weights(plan: dict[str, Any], names: list[str]) -> dict[str, float]:
    """画面に出す代表値。グループ別のときは平均を見せる。"""
    if plan["kind"] == "flat":
        return dict(plan["weights"])
    groups = plan["by_horizon"] if plan["kind"] == "horizon" else plan["by_family"]
    return {
        name: float(np.mean([part.get(name, 0.0) for part in groups.values()] or [0.0]))
        for name in names
    }


STRATEGY_PLANS: tuple[tuple[str, float], ...] = (
    ("rule", 1.0),
    ("fitted", 1.0),
    ("single", 1.0),
    ("fitted_horizon", 1.0),
    ("fitted_family", 1.0),
    ("fitted_family", 0.85),
    ("fitted_family", 0.7),
)


def _two_fold_score(
    pred_map: dict[str, pd.DataFrame],
    val: pd.DataFrame,
    halves: tuple[set[Any], set[Any]],
    strategy: str,
    alpha: float,
    train: pd.DataFrame,
    window: int,
    floor: float = 0.0,
    *,
    calibrate: bool = False,
    calibrate_shrink: float = 1.0,
    single_direction: bool = False,
) -> float:
    """片側で重みを当てはめ、もう片側で採点する。既定は両方向やって平均する。"""
    left, right = halves
    total = 0.0
    directions = ((left, right),) if single_direction else ((left, right), (right, left))
    for fit_ids, hold_ids in directions:
        fit_actual = val[val[ROW_ID].isin(fit_ids)]
        hold_actual = val[val[ROW_ID].isin(hold_ids)]
        plan = _fit_plan(strategy, _subset(pred_map, fit_ids), fit_actual, alpha)
        fit_raw = _apply_plan(plan, _subset(pred_map, fit_ids))
        hold_raw = _apply_plan(plan, _subset(pred_map, hold_ids))
        fit_candidate = zero_out_dead_series(train, fit_raw, window) if window else fit_raw
        hold_candidate = zero_out_dead_series(train, hold_raw, window) if window else hold_raw
        fit_candidate = snap_small_to_zero(fit_candidate, floor)
        hold_candidate = snap_small_to_zero(hold_candidate, floor)
        if calibrate:
            scales = fit_family_log_scales(fit_candidate, fit_actual, shrink=calibrate_shrink)
            hold_candidate = apply_family_log_scales(hold_candidate, scales)
        total += score_against(hold_candidate, hold_actual)
    return total / len(directions)


def family_row_ids(pred_map: dict[str, pd.DataFrame]) -> dict[str, set[Any]]:
    """売り場ごとの行。売り場別に顔ぶれを選ぶために使う。"""
    sample = next(iter(pred_map.values()))
    families = _family_of(sample)
    return {
        str(family): set(sample.loc[families == family, ROW_ID]) for family in families.unique()
    }


def _family_fold_score(
    pred_map: dict[str, pd.DataFrame],
    val: pd.DataFrame,
    halves: tuple[set[Any], set[Any]],
    train: pd.DataFrame,
    window: int,
    floor: float,
    rows: set[Any],
    *,
    single_direction: bool = False,
) -> float:
    """1つの売り場だけを、見ていない系列で採点する。

    `single_direction=True` なら片側で当てはめて反対側で採点する1回だけ。
    顔ぶれの選び方自体を診断するとき、採点に使う行を選択へ混ぜないために使う。
    """
    total = 0.0
    directions = (halves,) if single_direction else (halves, (halves[1], halves[0]))
    for fit_ids, hold_ids in directions:
        fit = fit_ids & rows
        hold = hold_ids & rows
        if not fit or not hold:
            raise ValueError("片側に行がありません")
        fit_actual = val[val[ROW_ID].isin(fit)]
        weights = fit_log_weights(_subset(pred_map, fit), fit_actual)
        held = blend(_subset(pred_map, hold), weights)
        held = zero_out_dead_series(train, held, window) if window else held
        held = snap_small_to_zero(held, floor)
        total += score_against(held, val[val[ROW_ID].isin(hold)])
    return total / len(directions)


def prune_by_family(
    pred_map: dict[str, pd.DataFrame],
    val: pd.DataFrame,
    halves: tuple[set[Any], set[Any]],
    train: pd.DataFrame,
    window: int,
    floor: float = 0.0,
    minimum: int = 1,
    *,
    single_direction: bool = False,
) -> dict[str, list[str]]:
    """売り場ごとに顔ぶれを選ぶ。

    売り場ごとに重みを当てるので、1つの売り場を1モデルに任せてもよい（minimum=1）。

    全体で1つの顔ぶれに絞ると、下着売り場のように少数派の棚にだけ効くモデルが
    消えてしまう。売り場ごとに「外して良くなるモデル」を落とせば、その棚だけで
    価値があるモデルを残せる。採点はどの売り場でも見ていない系列で行う。
    """
    subsets: dict[str, list[str]] = {}
    for family, rows in family_row_ids(pred_map).items():
        kept = dict(pred_map)
        try:
            best = _family_fold_score(
                kept, val, halves, train, window, floor, rows, single_direction=single_direction
            )
        except (ValueError, KeyError):
            subsets[family] = sorted(pred_map)
            continue
        while len(kept) > minimum:
            trials: dict[str, float] = {}
            for name in sorted(kept):
                trial = {key: frame for key, frame in kept.items() if key != name}
                try:
                    trials[name] = _family_fold_score(
                        trial,
                        val,
                        halves,
                        train,
                        window,
                        floor,
                        rows,
                        single_direction=single_direction,
                    )
                except (ValueError, KeyError):
                    continue
            if not trials:
                break
            candidate = min(trials, key=lambda name: trials[name])
            if trials[candidate] >= best - 1e-6:
                break
            best = trials[candidate]
            kept = {key: frame for key, frame in kept.items() if key != candidate}
        subsets[family] = sorted(kept)
    return subsets


def fit_family_subset_weights(
    pred_map: dict[str, pd.DataFrame],
    actual: pd.DataFrame,
    subsets: dict[str, list[str]],
) -> dict[str, dict[str, float]]:
    """売り場ごとに、その売り場で残ったモデルだけで重みを当てる。"""
    weights: dict[str, dict[str, float]] = {}
    for family, rows in family_row_ids(pred_map).items():
        names = [name for name in subsets.get(family, sorted(pred_map)) if name in pred_map]
        if not names:
            names = sorted(pred_map)
        subset = {name: pred_map[name][pred_map[name][ROW_ID].isin(rows)] for name in names}
        part = actual[actual[ROW_ID].isin(rows)]
        if part.empty:
            continue
        weights[family] = fit_log_weights(subset, part)
    return weights


def _family_subsets_two_fold_score(
    pred_map: dict[str, pd.DataFrame],
    val: pd.DataFrame,
    halves: tuple[set[Any], set[Any]],
    train: pd.DataFrame,
    window: int,
    floor: float,
    subsets: dict[str, list[str]],
) -> float:
    """売り場別の顔ぶれを、全行まとめて見ていない系列で採点する。"""
    total = 0.0
    for fit_ids, hold_ids in (halves, (halves[1], halves[0])):
        fit_weights = fit_family_subset_weights(
            _subset(pred_map, fit_ids), val[val[ROW_ID].isin(fit_ids)], subsets
        )
        held = blend_by_family(_subset(pred_map, hold_ids), fit_weights)
        held = zero_out_dead_series(train, held, window) if window else held
        held = snap_small_to_zero(held, floor)
        total += score_against(held, val[val[ROW_ID].isin(hold_ids)])
    return total / 2.0


def cross_fold_rule_scores(
    pred_map: dict[str, pd.DataFrame],
    val: pd.DataFrame,
    halves: tuple[set[Any], set[Any]],
    train: pd.DataFrame,
    window: int = 0,
    floor: float = 0.0,
    alpha: float = 1.0,
) -> dict[str, float]:
    """顔ぶれの選び方そのものを、選ぶのに使っていない行で採点する。

    いつもの二分割は「片側で重みを当て、もう片側で採点」する。しかし顔ぶれを選ぶ
    ときに両方向の平均を見ていると、採点する行を選択にも使ってしまう。ここでは
    片側だけで顔ぶれを決め、反対側で採点する（両向きの平均）。全体で1つの顔ぶれと、
    売り場ごとの顔ぶれを、同じ条件で比べるための診断。
    """
    left, right = halves
    totals = {"global": 0.0, "per_family": 0.0}
    for select, evaluate in ((left, right), (right, left)):
        select_halves = (select, evaluate)
        chosen, _ = _drop_models_that_do_not_earn_their_place(
            pred_map,
            val,
            select_halves,
            "fitted_family",
            alpha,
            train,
            window,
            single_direction=True,
        )
        subsets = prune_by_family(
            pred_map, val, select_halves, train, window, floor, single_direction=True
        )
        fit_actual = val[val[ROW_ID].isin(evaluate)]
        hold_actual = val[val[ROW_ID].isin(select)]

        kept = {name: pred_map[name] for name in chosen}
        plan = _fit_plan("fitted_family", _subset(kept, evaluate), fit_actual, alpha)
        held = _apply_plan(plan, _subset(kept, select))
        held = zero_out_dead_series(train, held, window) if window else held
        totals["global"] += score_against(snap_small_to_zero(held, floor), hold_actual)

        weights = fit_family_subset_weights(_subset(pred_map, evaluate), fit_actual, subsets)
        held = blend_by_family(_subset(pred_map, select), weights)
        held = zero_out_dead_series(train, held, window) if window else held
        totals["per_family"] += score_against(snap_small_to_zero(held, floor), hold_actual)
    return {name: value / 2.0 for name, value in totals.items()}


def _drop_models_that_do_not_earn_their_place(
    pred_map: dict[str, pd.DataFrame],
    val: pd.DataFrame,
    halves: tuple[set[Any], set[Any]],
    strategy: str,
    alpha: float,
    train: pd.DataFrame,
    window: int,
    minimum: int = 2,
    *,
    single_direction: bool = False,
) -> tuple[list[str], float]:
    """1つ外して良くなるモデルを順に落とす。

    重みの当てはめは行を見ているので、似たモデルを並べるほど当てはめ過ぎる。
    見ていない系列で採点して、悪化させるモデルだけを外す。
    """
    kept = dict(pred_map)
    best = _two_fold_score(
        kept, val, halves, strategy, alpha, train, window, single_direction=single_direction
    )
    while len(kept) > minimum:
        trials: dict[str, float] = {}
        for name in sorted(kept):
            trial = {key: frame for key, frame in kept.items() if key != name}
            try:
                trials[name] = _two_fold_score(
                    trial,
                    val,
                    halves,
                    strategy,
                    alpha,
                    train,
                    window,
                    single_direction=single_direction,
                )
            except (ValueError, KeyError):
                continue
        if not trials:
            break
        worst = min(trials, key=lambda name: trials[name])
        if trials[worst] >= best - 1e-6:
            break
        best = trials[worst]
        kept = {key: frame for key, frame in kept.items() if key != worst}
    return sorted(kept), best


def choose_blend(
    val_preds: dict[str, pd.DataFrame],
    test_preds: dict[str, pd.DataFrame],
    train: pd.DataFrame,
    val: pd.DataFrame,
    labeled: pd.DataFrame,
    windows: tuple[int, ...] = (0, 3, 7, 14, 21),
    floors: tuple[float, ...] = (0.0, 0.05, 0.1, 0.2, 0.3, 0.5, 0.8),
) -> dict[str, Any]:
    """使うモデル、混ぜ方、ゼロ窓を選ぶ。

    重みを当てはめた同じ行で選ぶと、グループ別の重みや似たモデルの重ね置きが
    必ず有利に見える。そこでファミリーごとに系列を2つに割り、片方で当てはめて
    もう片方で採点する（両方向の平均）。選んだ後だけ検証窓の全行で当てはめ直す。
    """
    scores = {name: score_against(frame, val) for name, frame in val_preds.items()}
    best_single = min(scores, key=lambda name: scores[name])
    halves = series_halves(val_preds)
    honest_ok = bool(halves[0] and halves[1])

    per_strategy: dict[str, float] = {}
    chosen_key: tuple[str, float, int] | None = None
    best_honest = float("inf")
    if honest_ok:
        for strategy, alpha in STRATEGY_PLANS:
            label = strategy if alpha == 1.0 else f"{strategy}_shrunk{alpha:g}"
            for window in windows:
                try:
                    value = _two_fold_score(val_preds, val, halves, strategy, alpha, train, window)
                except (ValueError, KeyError):
                    continue
                per_strategy[label] = min(per_strategy.get(label, float("inf")), value)
                if value < best_honest:
                    best_honest = value
                    chosen_key = (strategy, alpha, window)

    if chosen_key is None:
        # 系列が少なすぎて隠して採点できないときだけ、当てはめた点数で選ぶ。
        in_sample: dict[tuple[str, float, int], float] = {}
        for strategy, alpha in STRATEGY_PLANS:
            try:
                raw = _apply_plan(_fit_plan(strategy, val_preds, val, alpha), val_preds)
            except (ValueError, KeyError):
                continue
            for window in windows:
                candidate = zero_out_dead_series(train, raw, window) if window else raw
                in_sample[(strategy, alpha, window)] = score_against(candidate, val)
        if not in_sample:
            raise ValueError("混合候補がありません")
        chosen_key = min(in_sample, key=lambda item: in_sample[item])

    strategy, alpha, window = chosen_key
    used = sorted(val_preds)
    holdout_score: float | None = None
    floor = 0.0
    calibrate = False
    calibrate_shrink = 1.0
    family_scales: dict[str, float] = {}
    if honest_ok:
        used, holdout_score = _drop_models_that_do_not_earn_their_place(
            val_preds, val, halves, strategy, alpha, train, window
        )
        kept = {name: val_preds[name] for name in used}
        for window_option in windows:
            try:
                value = _two_fold_score(kept, val, halves, strategy, alpha, train, window_option)
            except (ValueError, KeyError):
                continue
            if value < holdout_score - 1e-9:
                holdout_score = value
                window = window_option
        for floor_option in floors:
            try:
                value = _two_fold_score(
                    kept, val, halves, strategy, alpha, train, window, floor_option
                )
            except (ValueError, KeyError):
                continue
            if value < holdout_score - 1e-9:
                holdout_score = value
                floor = floor_option
        for shrink in (0.5, 0.85, 1.0):
            try:
                value = _two_fold_score(
                    kept,
                    val,
                    halves,
                    strategy,
                    alpha,
                    train,
                    window,
                    floor,
                    calibrate=True,
                    calibrate_shrink=shrink,
                )
            except (ValueError, KeyError):
                continue
            if value < holdout_score - 1e-9:
                holdout_score = value
                calibrate = True
                calibrate_shrink = shrink

    family_subsets: dict[str, list[str]] | None = None
    if honest_ok and holdout_score is not None and not calibrate:
        try:
            subsets = prune_by_family(val_preds, val, halves, train, window, floor)
            value = _family_subsets_two_fold_score(
                val_preds, val, halves, train, window, floor, subsets
            )
        except (ValueError, KeyError):
            subsets, value = None, float("inf")
        if subsets is not None and value < holdout_score - 1e-9:
            holdout_score = value
            family_subsets = subsets
            strategy = "fitted_family_subsets"
            used = sorted({name for names in subsets.values() for name in names})

    val_used = {name: val_preds[name] for name in used}
    test_used = {name: test_preds[name] for name in used}
    if family_subsets is not None:
        by_family = fit_family_subset_weights(val_used, val, family_subsets)
        plan: dict[str, Any] = {
            "kind": "family",
            "by_family": by_family,
            "alpha": 1.0,
            "models_by_family": family_subsets,
        }
    else:
        plan = _fit_plan(strategy, val_used, val, alpha)
    val_raw = _apply_plan(plan, val_used)
    test_raw = _apply_plan(plan, test_used)
    val_blend = zero_out_dead_series(train, val_raw, window) if window else val_raw
    test_blend = zero_out_dead_series(labeled, test_raw, window) if window else test_raw
    val_blend = snap_small_to_zero(val_blend, floor)
    test_blend = snap_small_to_zero(test_blend, floor)
    if calibrate:
        family_scales = fit_family_log_scales(val_blend, val, shrink=calibrate_shrink)
        val_blend = apply_family_log_scales(val_blend, family_scales)
        test_blend = apply_family_log_scales(test_blend, family_scales)

    return {
        "strategy": strategy,
        "alpha": alpha,
        "zero_window": window,
        "small_floor": floor,
        "family_calibrate": calibrate,
        "family_calibrate_shrink": calibrate_shrink,
        "family_scales": family_scales,
        "val": val_blend,
        "test": test_blend,
        "weights": _mean_weights(plan, used),
        "weights_by_horizon": plan.get("by_horizon"),
        "weights_by_family": plan.get("by_family"),
        "models_by_family": plan.get("models_by_family"),
        "models_used": used,
        "best_single": best_single,
        "score": score_against(val_blend, val),
        "holdout_score": holdout_score,
        "candidates": per_strategy,
        "model_scores": scores,
    }


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
