"""特徴量。人が追える列だけを作る。

約束: 予測は16日先まで一度に出すので、売上ラグは16日以上しか使わない。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from retail_lab import DATE, ROW_ID, SERIES_ID, TARGET
from retail_lab.competitions.store_sales.data import Bundle

GBDT_FEATURES = [
    "lag_16",
    "lag_21",
    "lag_28",
    "lag_35",
    "roll_mean_7_lag16",
    "roll_mean_28_lag16",
    "onpromotion",
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
    "is_earthquake",
    "transactions_lag16",
    "store_nbr",
    "family",
    "type",
    "cluster",
]
CATEGORICALS = ["store_nbr", "family", "type", "cluster"]
# 未来側でも値が分かる列だけを Chronos-2 に渡す
CHRONOS_COVARIATES = ["onpromotion", "oil", "is_national_holiday", "is_payday"]


def _oil_by_date(oil: pd.DataFrame, dates: pd.Series) -> pd.DataFrame:
    """原油価格は週末が欠測。前日の値を持ち越す。"""
    calendar = pd.DataFrame({DATE: np.sort(pd.to_datetime(dates.unique()))})
    merged = calendar.merge(oil[[DATE, "dcoilwtico"]], on=DATE, how="left")
    merged["oil"] = merged["dcoilwtico"].ffill().bfill()
    merged["oil_lag7"] = merged["oil"].shift(7).bfill()
    return merged[[DATE, "oil", "oil_lag7"]]


def _holiday_flags(holidays: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    frame = holidays.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    real = frame[(frame["type"] != "Work Day") & (~frame["transferred"])]
    national = (
        real[real["locale"] == "National"][["date"]].drop_duplicates().assign(is_national_holiday=1)
    )
    local = (
        real[real["locale"] == "Local"][["date", "locale_name"]]
        .drop_duplicates()
        .rename(columns={"locale_name": "city"})
        .assign(is_local_holiday=1)
    )
    return national, local


def _calendar(dates: pd.Series) -> pd.DataFrame:
    days = pd.to_datetime(dates)
    month_end = days + pd.offsets.MonthEnd(0)
    return pd.DataFrame(
        {
            "dow": days.dt.weekday,
            "day": days.dt.day,
            "month": days.dt.month,
            "week": days.dt.isocalendar().week.astype(int),
            "is_weekend": (days.dt.weekday >= 5).astype(int),
            "is_payday": ((days.dt.day == 15) | (days == month_end)).astype(int),
        }
    )


def build_panel(bundle: Bundle) -> pd.DataFrame:
    """学習行と提出行を縦に積み、特徴まで作り終えた1枚の表を返す。"""
    train = bundle.train.copy()
    test = bundle.test.copy()
    test["sales"] = np.nan
    panel = pd.concat([train, test], ignore_index=True)

    panel = panel.rename(columns={"id": ROW_ID, "sales": TARGET})
    panel[SERIES_ID] = (
        panel["store_nbr"].astype(int).astype(str) + "::" + panel["family"].astype(str)
    )
    panel["onpromotion"] = panel["onpromotion"].fillna(0).astype(float)
    panel["promo_log"] = np.log1p(panel["onpromotion"])

    panel = panel.merge(bundle.stores, on="store_nbr", how="left")
    panel = panel.merge(_oil_by_date(bundle.oil, panel[DATE]), on=DATE, how="left")
    national, local = _holiday_flags(bundle.holidays)
    panel = panel.merge(national, on=DATE, how="left")
    panel = panel.merge(local, on=[DATE, "city"], how="left")
    panel["is_national_holiday"] = panel["is_national_holiday"].fillna(0).astype(int)
    panel["is_local_holiday"] = panel["is_local_holiday"].fillna(0).astype(int)

    panel = pd.concat(
        [panel.reset_index(drop=True), _calendar(panel[DATE]).reset_index(drop=True)], axis=1
    )
    # 2016-04-16の地震後は支援物資で通常と異なる売上が続いた
    panel["is_earthquake"] = (
        (panel[DATE] >= pd.Timestamp("2016-04-16")) & (panel[DATE] <= pd.Timestamp("2016-05-31"))
    ).astype(int)

    # 取引件数は売上より粗い店舗×日。16日前ならテスト最終日まで利用できる
    store_days = panel[["store_nbr", DATE]].drop_duplicates().sort_values(["store_nbr", DATE])
    transactions = store_days.merge(bundle.transactions, on=["store_nbr", DATE], how="left")
    last_transaction_day = bundle.transactions[DATE].max()
    historical = transactions[DATE] <= last_transaction_day
    transactions.loc[historical, "transactions"] = transactions.loc[
        historical, "transactions"
    ].fillna(0)
    transactions["transactions_lag16"] = transactions.groupby("store_nbr")["transactions"].shift(16)
    panel = panel.merge(
        transactions[["store_nbr", DATE, "transactions_lag16"]],
        on=["store_nbr", DATE],
        how="left",
    )

    panel = panel.sort_values([SERIES_ID, DATE]).reset_index(drop=True)
    grouped = panel.groupby(SERIES_ID, sort=False)[TARGET]
    for lag in (16, 21, 28, 35):
        panel[f"lag_{lag}"] = grouped.shift(lag)
    shifted = grouped.shift(16)
    panel["roll_mean_7_lag16"] = shifted.groupby(panel[SERIES_ID]).transform(
        lambda s: s.rolling(7, min_periods=3).mean()
    )
    panel["roll_mean_28_lag16"] = shifted.groupby(panel[SERIES_ID]).transform(
        lambda s: s.rolling(28, min_periods=7).mean()
    )
    return panel
