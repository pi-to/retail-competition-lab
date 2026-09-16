"""公式CSVの読み込み。無ければ Kaggle から取り、デモなら合成データを作る。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from retail_lab import kaggle
from retail_lab.competition import data_dir
from retail_lab.competitions.store_sales.spec import SPEC


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
    frame = pd.read_csv(path)
    if "date" in frame.columns:
        frame["date"] = pd.to_datetime(frame["date"])
    return frame


def files_present(target: Path) -> bool:
    return not kaggle.missing_files(target, list(SPEC.required_files))


def complete_daily_grid(train: pd.DataFrame) -> pd.DataFrame:
    """欠測日は売上0として埋める。基盤モデルは等間隔の系列を前提にする。

    埋めた行は提出対象ではないので、衝突しない負の id を振る。
    """
    keys = train[["store_nbr", "family"]].drop_duplicates()
    dates = pd.DataFrame(
        {"date": pd.date_range(train["date"].min(), train["date"].max(), freq="D")}
    )
    grid = keys.merge(dates, how="cross")
    out = grid.merge(train, on=["date", "store_nbr", "family"], how="left")
    out["sales"] = out["sales"].fillna(0.0)
    out["onpromotion"] = out["onpromotion"].fillna(0)
    invented = out["id"].isna()
    if invented.any():
        out.loc[invented, "id"] = -1 - np.arange(int(invented.sum()))
    out["id"] = out["id"].astype("int64")
    return out


def load_bundle(root: Path, source: str) -> Bundle:
    target = data_dir(root, SPEC.slug, source)
    if source == "kaggle":
        if not files_present(target):
            kaggle.download(root, SPEC.kaggle_slug, target, list(SPEC.required_files))
    elif not files_present(target):
        from retail_lab.competitions.store_sales.demo import generate_demo

        generate_demo(target)

    holidays = _read_csv(target / "holidays_events.csv")
    if "transferred" in holidays.columns:
        holidays["transferred"] = (
            holidays["transferred"].astype(str).str.lower().isin(["true", "1"])
        )
    return Bundle(
        train=complete_daily_grid(_read_csv(target / "train.csv")),
        test=_read_csv(target / "test.csv"),
        stores=_read_csv(target / "stores.csv"),
        oil=_read_csv(target / "oil.csv"),
        holidays=holidays,
        transactions=_read_csv(target / "transactions.csv"),
        source=source,
        data_dir=target,
    )
