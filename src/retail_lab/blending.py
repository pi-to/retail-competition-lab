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


def blend(pred_map: dict[str, pd.DataFrame], weights: dict[str, float]) -> pd.DataFrame:
    base: pd.DataFrame | None = None
    acc: np.ndarray | None = None
    order: np.ndarray | None = None
    for name, weight in weights.items():
        frame = pred_map[name].sort_values(ROW_ID)
        if base is None or acc is None or order is None:
            base = frame.drop(columns=[PRED]).copy()
            acc = np.zeros(len(frame), dtype=np.float64)
            order = frame[ROW_ID].to_numpy()
        aligned = frame.set_index(ROW_ID).loc[order, PRED].to_numpy()
        acc = acc + weight * aligned
    if base is None or acc is None:
        raise ValueError("混ぜるモデルがありません")
    out = base
    out[PRED] = np.clip(acc, 0, None)
    return out


def score_against(pred: pd.DataFrame, actual: pd.DataFrame) -> float:
    merged = pred.merge(actual[[ROW_ID, TARGET]], on=ROW_ID, how="inner")
    return rmsle(merged[TARGET], merged[PRED])


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
