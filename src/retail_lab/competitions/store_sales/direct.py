"""予測日ごとに「その時点で使えるラグ」を選ぶ一括 LightGBM。

16日先を予測するとき、1日先なら lag_7 は既知だが、8日先では未知になる。
そこで学習行にも1〜16日の予測距離を割り当て、距離に応じて利用可能な
直近値と同曜日の週次ラグを選ぶ。予測値を次の日へ戻さないため誤差が連鎖しない。
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor

from retail_lab import DATE, ROW_ID, SERIES_ID, TARGET
from retail_lab.competitions.store_sales.recursive import BASE_FEATURES

HORIZON_FEATURE = "forecast_horizon"
DYNAMIC_LAGS = ["origin_value", "weekly_0", "weekly_1", "weekly_2", "weekly_3"]
FEATURES = [*DYNAMIC_LAGS, HORIZON_FEATURE, *BASE_FEATURES, "family"]
CATEGORICALS = ["store_nbr", "type", "cluster", "family"]
OUTPUT = [ROW_ID, DATE, SERIES_ID, "pred"]


def _horizons(dates: pd.Series, horizon: int) -> pd.Series:
    """各学習日に1〜horizonを均等に割り当てる。"""
    ordinal = (pd.to_datetime(dates) - pd.Timestamp("1970-01-01")).dt.days
    return (ordinal % horizon + 1).astype(int)


def _add_dynamic_lags(frame: pd.DataFrame, horizons: pd.Series) -> pd.DataFrame:
    out = frame.copy()
    grouped = out.groupby(SERIES_ID, sort=False)[TARGET]
    horizon_values = horizons.to_numpy(dtype=int)
    week_base = 7 * np.ceil(horizon_values / 7).astype(int)
    lag_numbers = sorted(
        set(horizon_values.tolist())
        | {int(base + extra) for base in week_base for extra in (0, 7, 14, 21)}
    )
    shifted = {lag: grouped.shift(lag).to_numpy() for lag in lag_numbers}
    out["origin_value"] = np.array(
        [shifted[h][row] for row, h in enumerate(horizon_values)], dtype=float
    )
    for index, extra in enumerate((0, 7, 14, 21)):
        out[f"weekly_{index}"] = np.array(
            [shifted[int(base + extra)][row] for row, base in enumerate(week_base)],
            dtype=float,
        )
    out[HORIZON_FEATURE] = horizon_values
    return out


def fit_predict(
    train: pd.DataFrame,
    future: pd.DataFrame,
    *,
    n_estimators: int = 360,
    context_days: int = 730,
) -> tuple[pd.DataFrame, list[dict[str, float | str]]]:
    """未来の正解を読まず、全予測日を直接予測する。"""
    future_clean = future.drop(columns=[TARGET], errors="ignore").copy()
    horizon = int(future_clean[DATE].nunique())
    if horizon < 1:
        raise ValueError("予測日がありません")

    cutoff = train[DATE].max() - pd.Timedelta(days=context_days + 42)
    recent = train[train[DATE] > cutoff].sort_values([SERIES_ID, DATE]).copy()
    train_horizons = _horizons(recent[DATE], horizon)
    featured = _add_dynamic_lags(recent, train_horizons)
    featured = featured[featured[DATE] > train[DATE].max() - pd.Timedelta(days=context_days)]
    featured = featured.dropna(subset=DYNAMIC_LAGS)

    history = recent.set_index([SERIES_ID, DATE])[TARGET]
    origin = train[DATE].max()
    future_clean[HORIZON_FEATURE] = (future_clean[DATE] - origin).dt.days.astype(int)
    for name in DYNAMIC_LAGS:
        future_clean[name] = np.nan
    for index, row in future_clean.iterrows():
        step = int(row[HORIZON_FEATURE])
        weekly = 7 * int(np.ceil(step / 7))
        lags = [step, weekly, weekly + 7, weekly + 14, weekly + 21]
        values = [
            history.get((row[SERIES_ID], row[DATE] - pd.Timedelta(days=lag)), np.nan)
            for lag in lags
        ]
        future_clean.loc[index, DYNAMIC_LAGS] = values

    x = featured[FEATURES].copy()
    future_x = future_clean[FEATURES].copy()
    for column in CATEGORICALS:
        x[column] = x[column].astype("category")
        future_x[column] = pd.Categorical(future_x[column], categories=x[column].cat.categories)

    model = LGBMRegressor(
        n_estimators=n_estimators,
        learning_rate=0.04,
        num_leaves=63,
        min_child_samples=40,
        subsample=0.85,
        colsample_bytree=0.9,
        reg_lambda=0.7,
        random_state=42,
        verbose=-1,
        n_jobs=-1,
    )
    model.fit(
        x,
        np.log1p(featured[TARGET].clip(lower=0)),
        categorical_feature=CATEGORICALS,
    )
    future_clean["pred"] = np.clip(np.expm1(model.predict(future_x)), 0, None)
    importance: list[dict[str, Any]] = [
        {"feature": name, "gain": float(gain)}
        for name, gain in sorted(
            zip(FEATURES, model.feature_importances_, strict=True),
            key=lambda item: -item[1],
        )
    ]
    return future_clean[OUTPUT], importance
