"""検証の切り方。テストと同じ長さの窓を学習末尾から取る。"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from retail_lab import DATE, TARGET


@dataclass(frozen=True)
class Split:
    """``panel`` を3つに割った結果。

    - ``train``: 学習に使う（検証窓より前）
    - ``val``: 答え合わせに使う（学習末尾の horizon 日）
    - ``future``: 提出対象（target が無い行）
    """

    train: pd.DataFrame
    val: pd.DataFrame
    future: pd.DataFrame
    val_start: pd.Timestamp

    @property
    def labeled(self) -> pd.DataFrame:
        """学習 + 検証。提出用モデルはこれ全部で学習する。"""
        return pd.concat([self.train, self.val], ignore_index=True)


def split_panel(panel: pd.DataFrame, horizon: int) -> Split:
    known = panel[panel[TARGET].notna()]
    future = panel[panel[TARGET].isna()].copy()
    last = known[DATE].max()
    val_start = last - pd.Timedelta(days=horizon - 1)
    return Split(
        train=known[known[DATE] < val_start].copy(),
        val=known[known[DATE] >= val_start].copy(),
        future=future,
        val_start=val_start,
    )
