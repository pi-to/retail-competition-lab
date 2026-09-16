from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from demo import generate_demo

HORIZON = 16
REQUIRED = [
    "train.csv",
    "test.csv",
    "stores.csv",
    "oil.csv",
    "holidays_events.csv",
    "transactions.csv",
]


@dataclass
class Bundle:
    train: pd.DataFrame
    test: pd.DataFrame
    stores: pd.DataFrame
    oil: pd.DataFrame
    holidays: pd.DataFrame
    transactions: pd.DataFrame
    source: str
    data_dir: Path


def _read_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
    return df


def complete_daily_grid(train: pd.DataFrame) -> pd.DataFrame:
    """欠測日は売上0。Chronos / TimesFM は等間隔系列が前提。"""
    keys = train[["store_nbr", "family"]].drop_duplicates()
    dates = pd.DataFrame({"date": pd.date_range(train["date"].min(), train["date"].max(), freq="D")})
    grid = keys.merge(dates, how="cross")
    out = grid.merge(train, on=["date", "store_nbr", "family"], how="left")
    out["sales"] = out["sales"].fillna(0.0)
    out["onpromotion"] = out["onpromotion"].fillna(0)
    if out["id"].isna().any():
        max_id = int(train["id"].max())
        missing = out["id"].isna()
        out.loc[missing, "id"] = max_id + 1 + np.arange(missing.sum())
        out["id"] = out["id"].astype(int)
    return out


def has_kaggle_files(data_dir: Path) -> bool:
    return all((data_dir / name).exists() for name in REQUIRED)


def load_bundle(root: Path, source: str) -> Bundle:
    if source == "kaggle":
        data_dir = root / "data" / "kaggle"
        if not has_kaggle_files(data_dir):
            raise FileNotFoundError(
                "data/kaggle に公式CSVがありません。Kaggleからダウンロードして配置してください。"
            )
    else:
        data_dir = root / "data" / "demo"
        if not has_kaggle_files(data_dir):
            generate_demo(data_dir)

    train = _read_csv(data_dir / "train.csv")
    test = _read_csv(data_dir / "test.csv")
    stores = _read_csv(data_dir / "stores.csv")
    oil = _read_csv(data_dir / "oil.csv")
    holidays = _read_csv(data_dir / "holidays_events.csv")
    transactions = _read_csv(data_dir / "transactions.csv")
    if "transferred" in holidays.columns:
        holidays["transferred"] = holidays["transferred"].astype(str).str.lower().isin(["true", "1"])
    train = complete_daily_grid(train)
    return Bundle(train, test, stores, oil, holidays, transactions, source, data_dir)


def series_id(store_nbr: int, family: str) -> str:
    return f"{int(store_nbr)}::{family}"


def add_series_id(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["series_id"] = out["store_nbr"].astype(int).astype(str) + "::" + out["family"].astype(str)
    return out


def split_holdout(train: pd.DataFrame, horizon: int = HORIZON) -> tuple[pd.DataFrame, pd.DataFrame]:
    last = train["date"].max()
    cut = last - pd.Timedelta(days=horizon - 1)
    hist = train[train["date"] < cut].copy()
    val = train[train["date"] >= cut].copy()
    return hist, val
