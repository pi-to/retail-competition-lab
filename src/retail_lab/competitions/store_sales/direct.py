"""予測日ごとに「その時点で使えるラグ」を選ぶ一括 LightGBM。

16日先を予測するとき、1日先なら lag_7 は既知だが、8日先では未知になる。
そこで学習行にも1〜horizonの予測距離を割り当て、距離に応じて利用可能な
直近値と同曜日の週次ラグを選ぶ。予測値を次の日へ戻さないため誤差が連鎖しない。
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier, LGBMRegressor

from retail_lab import DATE, ROW_ID, SERIES_ID, TARGET
from retail_lab.competitions.store_sales.recursive import (
    BASE_FEATURES,
    INTERMITTENT_FEATURES,
    LEVEL_WINDOW,
    SALE_GAP_CAP,
    SALE_THRESHOLD,
    ZERO_WINDOW,
)

HORIZON_FEATURE = "forecast_horizon"
DYNAMIC_LAGS = ["origin_value", "weekly_0", "weekly_1", "weekly_2", "weekly_3"]
BASE_DIRECT = [*DYNAMIC_LAGS, HORIZON_FEATURE, *BASE_FEATURES, "family"]
FEATURES = list(BASE_DIRECT)
INTERMITTENT_DIRECT = [*BASE_DIRECT, *INTERMITTENT_FEATURES]
FAMILY_TREND_FEATURES = [
    "family_mean_7",
    "family_mean_28",
    "family_level_ratio_7_56",
    "family_same_dow_4",
]
FAMILY_TREND_DIRECT = [*INTERMITTENT_DIRECT, *FAMILY_TREND_FEATURES]
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


def _state_through_each_day(values: np.ndarray) -> dict[str, np.ndarray]:
    """その日までの実績で見た間欠状態。index i は values[: i+1] まで見た結果。"""
    n = len(values)
    zero_rate = np.full(n, np.nan)
    sale_mean = np.zeros(n)
    level_ratio = np.full(n, np.nan)
    dow_mean = np.full(n, np.nan)
    gap_through = np.full(n, float(SALE_GAP_CAP))
    last_sale = -1
    prefix = np.cumsum(values, dtype=float)
    sold_mask = values >= SALE_THRESHOLD
    sold_prefix = np.cumsum(sold_mask.astype(float), dtype=float)
    sale_sum_prefix = np.cumsum(np.where(sold_mask, values, 0.0), dtype=float)
    for i, value in enumerate(values):
        if value >= SALE_THRESHOLD:
            last_sale = i
        # 最後に売れた日からの経過。今日売れていれば1。
        gap_through[i] = float(i - last_sale + 1) if last_sale >= 0 else float(SALE_GAP_CAP)
        gap_through[i] = min(gap_through[i], float(SALE_GAP_CAP))
        start = max(0, i + 1 - ZERO_WINDOW)
        far_start = max(0, i + 1 - LEVEL_WINDOW)
        window_len = i + 1 - start
        if window_len >= ZERO_WINDOW:
            recent_sum = prefix[i] - (prefix[start - 1] if start else 0.0)
            recent_sold = sold_prefix[i] - (sold_prefix[start - 1] if start else 0.0)
            recent_sale_sum = sale_sum_prefix[i] - (sale_sum_prefix[start - 1] if start else 0.0)
            zero_rate[i] = 1.0 - recent_sold / window_len
            near_mean = recent_sum / window_len
            far_len = i + 1 - far_start
            far_sum = prefix[i] - (prefix[far_start - 1] if far_start else 0.0)
            far_mean = far_sum / far_len
            level_ratio[i] = (near_mean + 1.0) / (far_mean + 1.0)
            sale_mean[i] = recent_sale_sum / recent_sold if recent_sold > 0 else 0.0
        weekday = [values[i - lag] for lag in (7, 14, 21, 28) if i - lag >= 0]
        dow_mean[i] = float(np.mean(weekday)) if weekday else np.nan
    return {
        "recursive_days_since_sale": gap_through,
        "recursive_zero_rate_28": zero_rate,
        "recursive_sale_mean_28": sale_mean,
        "recursive_level_ratio": level_ratio,
        "recursive_dow_mean_4": dow_mean,
    }


def _origin_states(frame: pd.DataFrame) -> pd.DataFrame:
    """系列×日付ごとに、その日までの実績で見た間欠状態を返す。"""
    pieces: list[pd.DataFrame] = []
    for _sid, group in frame.sort_values(DATE).groupby(SERIES_ID, sort=False):
        values = group[TARGET].astype(float).clip(lower=0).to_numpy()
        state = _state_through_each_day(values)
        part = group[[SERIES_ID, DATE]].copy()
        for name, column in state.items():
            part[name] = column
        pieces.append(part)
    return pd.concat(pieces, ignore_index=True)


def _attach_intermittent(
    frame: pd.DataFrame,
    states: pd.DataFrame,
    horizons: pd.Series | np.ndarray,
    *,
    fixed_origin: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """各行の予測起点までの状態を付け、間隔だけ予測日ぶん伸ばす。"""
    out = frame.copy()
    horizon_values = (
        horizons.to_numpy(dtype=int)
        if isinstance(horizons, pd.Series)
        else np.asarray(horizons, dtype=int)
    )
    if fixed_origin is None:
        origins = pd.to_datetime(out[DATE]) - pd.to_timedelta(horizon_values, unit="D")
    else:
        origins = pd.Series(fixed_origin, index=out.index)
    lookup = out[[SERIES_ID]].copy()
    lookup["_origin"] = origins.to_numpy()
    merged = lookup.merge(
        states.rename(columns={DATE: "_origin"}),
        on=[SERIES_ID, "_origin"],
        how="left",
    )
    for name in INTERMITTENT_FEATURES:
        out[name] = merged[name].to_numpy()
    out["recursive_days_since_sale"] = np.minimum(
        out["recursive_days_since_sale"].fillna(SALE_GAP_CAP).to_numpy() + horizon_values,
        float(SALE_GAP_CAP),
    )
    return out


def _family_states(frame: pd.DataFrame) -> pd.DataFrame:
    """各売り場の全店舗平均から、共通する直近の勢いを日ごとに作る。"""
    daily = (
        frame.groupby(["family", DATE])[TARGET]
        .mean()
        .rename(TARGET)
        .reset_index()
        .sort_values(["family", DATE])
    )
    pieces: list[pd.DataFrame] = []
    for _family, group in daily.groupby("family", sort=False):
        part = group.copy()
        values = part[TARGET].astype(float)
        part["family_mean_7"] = values.rolling(7, min_periods=7).mean()
        part["family_mean_28"] = values.rolling(28, min_periods=28).mean()
        far = values.rolling(56, min_periods=28).mean()
        part["family_level_ratio_7_56"] = (part["family_mean_7"] + 1.0) / (far + 1.0)
        part["family_same_dow_4"] = pd.concat(
            [values.shift(lag) for lag in (7, 14, 21, 28)], axis=1
        ).mean(axis=1)
        pieces.append(part[["family", DATE, *FAMILY_TREND_FEATURES]])
    return pd.concat(pieces, ignore_index=True)


def _attach_family_trend(
    frame: pd.DataFrame,
    states: pd.DataFrame,
    horizons: pd.Series | np.ndarray,
    *,
    fixed_origin: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """各予測行に、予測起点までに確定した売り場全体の勢いを付ける。"""
    out = frame.copy()
    horizon_values = (
        horizons.to_numpy(dtype=int)
        if isinstance(horizons, pd.Series)
        else np.asarray(horizons, dtype=int)
    )
    origins = (
        pd.to_datetime(out[DATE]) - pd.to_timedelta(horizon_values, unit="D")
        if fixed_origin is None
        else pd.Series(fixed_origin, index=out.index)
    )
    lookup = out[["family"]].copy()
    lookup["_origin"] = origins.to_numpy()
    merged = lookup.merge(
        states.rename(columns={DATE: "_origin"}),
        on=["family", "_origin"],
        how="left",
    )
    for name in FAMILY_TREND_FEATURES:
        out[name] = merged[name].to_numpy()
    return out


def fit_predict(
    train: pd.DataFrame,
    future: pd.DataFrame,
    *,
    n_estimators: int = 360,
    context_days: int = 730,
    intermittent: bool = False,
    hurdle: bool = False,
    family_trend: bool = False,
) -> tuple[pd.DataFrame, list[dict[str, float | str]]]:
    """未来の正解を読まず、全予測日を直接予測する。

    `intermittent=True` は、予測の起点までに売れていない日の続き方と水準の動きを足す。
    `hurdle=True` は「売れるか」と「売れたらいくらか」を分けて学び、掛けて戻す。
    """
    if hurdle and not intermittent:
        raise ValueError("hurdle は intermittent=True のときだけ使えます")
    if family_trend and not intermittent:
        raise ValueError("family_trend は intermittent=True のときだけ使えます")
    columns = (
        FAMILY_TREND_DIRECT if family_trend else INTERMITTENT_DIRECT if intermittent else FEATURES
    )
    future_clean = future.drop(columns=[TARGET], errors="ignore").copy()
    horizon = int(future_clean[DATE].nunique())
    if horizon < 1:
        raise ValueError("予測日がありません")

    cutoff = train[DATE].max() - pd.Timedelta(days=context_days + 42)
    recent = train[train[DATE] > cutoff].sort_values([SERIES_ID, DATE]).copy()
    train_horizons = _horizons(recent[DATE], horizon)
    featured = _add_dynamic_lags(recent, train_horizons)
    states = _origin_states(recent) if intermittent else None
    family_states = _family_states(recent) if family_trend else None
    if intermittent and states is not None:
        featured = _attach_intermittent(featured, states, train_horizons)
    if family_trend and family_states is not None:
        featured = _attach_family_trend(featured, family_states, train_horizons)
    featured = featured[featured[DATE] > train[DATE].max() - pd.Timedelta(days=context_days)]
    featured = featured.dropna(subset=DYNAMIC_LAGS)

    origin = train[DATE].max()
    future_clean[HORIZON_FEATURE] = (future_clean[DATE] - origin).dt.days.astype(int)
    for name in DYNAMIC_LAGS:
        future_clean[name] = np.nan
    history = recent.set_index([SERIES_ID, DATE])[TARGET]
    for index, row in future_clean.iterrows():
        step = int(row[HORIZON_FEATURE])
        weekly = 7 * int(np.ceil(step / 7))
        lags = [step, weekly, weekly + 7, weekly + 14, weekly + 21]
        values = [
            history.get((row[SERIES_ID], row[DATE] - pd.Timedelta(days=lag)), np.nan)
            for lag in lags
        ]
        future_clean.loc[index, DYNAMIC_LAGS] = values
    if intermittent and states is not None:
        future_clean = _attach_intermittent(
            future_clean, states, future_clean[HORIZON_FEATURE].to_numpy(), fixed_origin=origin
        )
    if family_trend and family_states is not None:
        future_clean = _attach_family_trend(
            future_clean,
            family_states,
            future_clean[HORIZON_FEATURE].to_numpy(),
            fixed_origin=origin,
        )

    x = featured[columns].copy()
    future_x = future_clean[columns].copy()
    for column in CATEGORICALS:
        x[column] = x[column].astype("category")
        future_x[column] = pd.Categorical(future_x[column], categories=x[column].cat.categories)

    params: dict[str, Any] = {
        "n_estimators": n_estimators,
        "learning_rate": 0.04,
        "num_leaves": 63,
        "min_child_samples": 40,
        "subsample": 0.85,
        "colsample_bytree": 0.9,
        "reg_lambda": 0.7,
        "random_state": 42,
        "verbose": -1,
        "n_jobs": -1,
    }
    model = LGBMRegressor(**params)
    sold = (featured[TARGET] >= SALE_THRESHOLD).to_numpy()
    gate: LGBMClassifier | None = None
    if hurdle and sold.any() and not sold.all():
        gate = LGBMClassifier(**params)
        gate.fit(x, sold.astype(int), categorical_feature=CATEGORICALS)
        model.fit(
            x[sold],
            np.log1p(featured.loc[sold, TARGET].clip(lower=0)),
            categorical_feature=CATEGORICALS,
        )
    else:
        model.fit(
            x,
            np.log1p(featured[TARGET].clip(lower=0)),
            categorical_feature=CATEGORICALS,
        )

    raw = model.predict(future_x)
    if gate is not None:
        chance = np.asarray(gate.predict_proba(future_x))[:, 1]
        future_clean["pred"] = np.clip(np.expm1(chance * np.clip(raw, 0, None)), 0, None)
    else:
        future_clean["pred"] = np.clip(np.expm1(raw), 0, None)

    importance: list[dict[str, Any]] = [
        {"feature": name, "gain": float(gain)}
        for name, gain in sorted(
            zip(columns, model.feature_importances_, strict=True),
            key=lambda item: -item[1],
        )
    ]
    return future_clean[OUTPUT], importance
