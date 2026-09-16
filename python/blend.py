from __future__ import annotations

import numpy as np
import pandas as pd

from metrics import rmsle


def inverse_rmsle_weights(scores: dict[str, float]) -> dict[str, float]:
    usable = {k: v for k, v in scores.items() if np.isfinite(v) and v > 0}
    if not usable:
        return {}
    inv = {k: 1.0 / v for k, v in usable.items()}
    z = sum(inv.values())
    return {k: float(v / z) for k, v in inv.items()}


def blend(pred_map: dict[str, pd.DataFrame], weights: dict[str, float]) -> pd.DataFrame:
    base = None
    acc = None
    for name, w in weights.items():
        df = (
            pred_map[name][["id", "date", "series_id", "store_nbr", "family", "pred"]]
            .copy()
            .sort_values("id")
        )
        if base is None:
            base = df.drop(columns=["pred"]).copy()
            acc = np.zeros(len(df), dtype=np.float64)
            id_order = df["id"].to_numpy()
        aligned = df.set_index("id").loc[id_order]["pred"].to_numpy()
        acc = acc + w * aligned
    out = base.copy()
    out["pred"] = np.clip(acc, 0, None)
    return out


def score_against(pred: pd.DataFrame, actual: pd.DataFrame) -> float:
    m = pred.merge(actual[["id", "sales"]], on="id", how="inner")
    return rmsle(m["sales"], m["pred"])


def zero_sales_rule(history: pd.DataFrame, pred: pd.DataFrame, lookback: int = 21) -> pd.DataFrame:
    """直近 lookback 日がすべて 0 なら、閉シリーズとみなして 0 を出す。"""
    from data import add_series_id

    hist = add_series_id(history)
    last = hist["date"].max()
    window = hist[hist["date"] > last - pd.Timedelta(days=lookback)]
    zeros = window.groupby("series_id")["sales"].sum()
    dead = set(zeros[zeros <= 0].index)
    out = pred.copy()
    out.loc[out["series_id"].isin(dead), "pred"] = 0.0
    return out
