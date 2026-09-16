"""同じ曜日の直近実績。どのコンペでも下限として置く。"""

from __future__ import annotations

import pandas as pd

from retail_lab import DATE, ROW_ID, SERIES_ID, TARGET

OUTPUT_COLUMNS = [ROW_ID, DATE, SERIES_ID, "pred"]


def seasonal_naive(history: pd.DataFrame, future: pd.DataFrame) -> pd.DataFrame:
    hist = history.copy()
    hist["dow"] = hist[DATE].dt.weekday
    last = (
        hist.sort_values(DATE)
        .groupby([SERIES_ID, "dow"], as_index=False)
        .tail(1)[[SERIES_ID, "dow", TARGET]]
        .rename(columns={TARGET: "pred"})
    )
    out = future[[ROW_ID, DATE, SERIES_ID]].copy()
    out["dow"] = out[DATE].dt.weekday
    out = out.merge(last, on=[SERIES_ID, "dow"], how="left")
    fallback = hist.groupby(SERIES_ID)[TARGET].median()
    out["pred"] = out["pred"].fillna(out[SERIES_ID].map(fallback)).fillna(0.0).clip(lower=0.0)
    return out[OUTPUT_COLUMNS]
