"""同じ曜日の直近実績。『何もしない』下限。"""

from __future__ import annotations

import pandas as pd

from data import add_series_id


def seasonal_naive(history: pd.DataFrame, future: pd.DataFrame) -> pd.DataFrame:
    hist = add_series_id(history).copy()
    fut = add_series_id(future).copy()
    hist["dow"] = hist["date"].dt.weekday
    last = (
        hist.sort_values("date")
        .groupby(["series_id", "dow"], as_index=False)
        .tail(1)[["series_id", "dow", "sales"]]
        .rename(columns={"sales": "pred"})
    )
    fut["dow"] = fut["date"].dt.weekday
    out = fut.merge(last, on=["series_id", "dow"], how="left")
    fallback = hist.groupby("series_id")["sales"].median()
    out["pred"] = out["pred"].fillna(out["series_id"].map(fallback)).fillna(0.0).clip(lower=0.0)
    return out[["id", "date", "series_id", "store_nbr", "family", "pred"]]
