"""人間が追える特徴だけ。未来16日に届かないラグ（1〜15）は使わない。"""

from __future__ import annotations

import numpy as np
import pandas as pd

from data import add_series_id


def _oil_filled(oil: pd.DataFrame, dates: pd.Series) -> pd.DataFrame:
    cal = pd.DataFrame({"date": np.sort(pd.to_datetime(dates.unique()))})
    merged = cal.merge(oil[["date", "dcoilwtico"]], on="date", how="left")
    merged["oil"] = merged["dcoilwtico"].ffill().bfill()
    merged["oil_lag7"] = merged["oil"].shift(7).bfill()
    return merged[["date", "oil", "oil_lag7"]]


def _holiday_flags(holidays: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    h = holidays.copy()
    h["date"] = pd.to_datetime(h["date"])
    real = h[(h["type"] != "Work Day") & (~h["transferred"])]
    national = (
        real[real["locale"] == "National"][["date"]]
        .drop_duplicates()
        .assign(is_national_holiday=1)
    )
    local = (
        real[real["locale"] == "Local"][["date", "locale_name"]]
        .drop_duplicates()
        .rename(columns={"locale_name": "city"})
        .assign(is_local_holiday=1)
    )
    return national, local


def calendar_frame(dates: pd.Series) -> pd.DataFrame:
    d = pd.to_datetime(dates)
    month_end = d + pd.offsets.MonthEnd(0)
    return pd.DataFrame(
        {
            "date": d,
            "dow": d.dt.weekday,
            "day": d.dt.day,
            "month": d.dt.month,
            "week": d.dt.isocalendar().week.astype(int),
            "is_weekend": (d.dt.weekday >= 5).astype(int),
            "is_payday": ((d.dt.day == 15) | (d == month_end)).astype(int),
        }
    )


def attach_static(df: pd.DataFrame, stores: pd.DataFrame, oil: pd.DataFrame, holidays: pd.DataFrame) -> pd.DataFrame:
    out = add_series_id(df)
    out = out.merge(stores, on="store_nbr", how="left")
    oil_f = _oil_filled(oil, out["date"])
    out = out.merge(oil_f, on="date", how="left")
    national, local = _holiday_flags(holidays)
    out = out.merge(national, on="date", how="left")
    out = out.merge(local, on=["date", "city"], how="left")
    out["is_national_holiday"] = out["is_national_holiday"].fillna(0).astype(int)
    out["is_local_holiday"] = out["is_local_holiday"].fillna(0).astype(int)
    cal = calendar_frame(out["date"])
    out = pd.concat([out.reset_index(drop=True), cal.drop(columns=["date"]).reset_index(drop=True)], axis=1)
    return out


def add_lag_features(panel: pd.DataFrame) -> pd.DataFrame:
    """sales がある行だけでラグを作り、test 側へも series ごとに過去を接合する。"""
    out = panel.sort_values(["series_id", "date"]).copy()
    g = out.groupby("series_id", sort=False)["sales"]
    for lag in (16, 21, 28, 35):
        out[f"lag_{lag}"] = g.shift(lag)
    shifted = g.shift(16)
    out["roll_mean_7_lag16"] = shifted.groupby(out["series_id"]).transform(lambda s: s.rolling(7, min_periods=3).mean())
    out["roll_mean_28_lag16"] = shifted.groupby(out["series_id"]).transform(lambda s: s.rolling(28, min_periods=7).mean())
    out["promo"] = out["onpromotion"].fillna(0).astype(float)
    out["promo_log"] = np.log1p(out["promo"])
    return out


LGBM_FEATURES = [
    "lag_16",
    "lag_21",
    "lag_28",
    "lag_35",
    "roll_mean_7_lag16",
    "roll_mean_28_lag16",
    "promo",
    "promo_log",
    "oil",
    "oil_lag7",
    "dow",
    "day",
    "month",
    "week",
    "is_weekend",
    "is_payday",
    "is_national_holiday",
    "is_local_holiday",
    "store_nbr",
    "family",
    "type",
    "cluster",
]
CAT_FEATURES = ["store_nbr", "family", "type", "cluster"]
