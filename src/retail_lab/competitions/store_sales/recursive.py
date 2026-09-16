"""商品ファミリー別 LightGBM を1日ずつ前へ進める再帰予測。

1日目の予測を履歴へ足し、2日目ではそれを `lag_1` として使う。
これで16日一括予測では使えなかった直近1・7・14日の週次リズムを安全に使える。
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor

from retail_lab import DATE, ROW_ID, SERIES_ID, TARGET

LAGS = (1, 7, 14, 16, 21, 28, 35, 42, 49, 56, 63)
ROLLS = (7, 14, 28)
BASE_FEATURES = [
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
    "type",
    "cluster",
]
LAG_FEATURES = [f"recursive_lag_{lag}" for lag in LAGS]
ROLL_FEATURES = [f"recursive_roll_{window}" for window in ROLLS]
FEATURES = [*LAG_FEATURES, *ROLL_FEATURES, *BASE_FEATURES]
CATEGORICALS = ["store_nbr", "type", "cluster"]
OUTPUT = [ROW_ID, DATE, SERIES_ID, "pred"]


def _training_features(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.sort_values([SERIES_ID, DATE]).copy()
    grouped = out.groupby(SERIES_ID, sort=False)[TARGET]
    for lag in LAGS:
        out[f"recursive_lag_{lag}"] = grouped.shift(lag)
    shifted = grouped.shift(1)
    for window in ROLLS:
        out[f"recursive_roll_{window}"] = shifted.groupby(out[SERIES_ID]).transform(
            lambda series, size=window: series.rolling(size, min_periods=size).mean()
        )
    return out


def _future_features(row: pd.Series, values: list[float]) -> dict[str, Any]:
    features = {name: row[name] for name in BASE_FEATURES}
    for lag in LAGS:
        features[f"recursive_lag_{lag}"] = values[-lag] if len(values) >= lag else np.nan
    for window in ROLLS:
        features[f"recursive_roll_{window}"] = (
            float(np.mean(values[-window:])) if len(values) >= window else np.nan
        )
    return features


def fit_predict(
    train: pd.DataFrame,
    future: pd.DataFrame,
    *,
    n_estimators: int = 220,
    context_days: int = 730,
) -> tuple[pd.DataFrame, list[dict[str, float | str]]]:
    """ファミリーごとに学習し、未来を日ごとに再帰予測する。

    `future[TARGET]` は一切読まない。検証時に答えが同じDataFrame内にあっても漏洩しない。
    """
    cutoff = train[DATE].max() - pd.Timedelta(days=context_days)
    recent = train[train[DATE] > cutoff]
    featured = _training_features(recent)
    future_clean = future.drop(columns=[TARGET], errors="ignore")

    predictions: list[pd.DataFrame] = []
    importance: defaultdict[str, float] = defaultdict(float)
    families = list(dict.fromkeys(future_clean["family"].tolist()))

    for family in families:
        family_train = featured[featured["family"] == family].dropna(
            subset=[f"recursive_lag_{max(LAGS)}"]
        )
        family_future = future_clean[future_clean["family"] == family].sort_values(DATE)
        if family_train.empty:
            continue

        x = family_train[FEATURES].copy()
        categories: dict[str, pd.Index] = {}
        for column in CATEGORICALS:
            x[column] = x[column].astype("category")
            categories[column] = x[column].cat.categories

        model = LGBMRegressor(
            n_estimators=n_estimators,
            learning_rate=0.045,
            num_leaves=31,
            max_depth=-1,
            min_child_samples=30,
            subsample=0.85,
            colsample_bytree=0.85,
            reg_lambda=0.5,
            random_state=42,
            verbose=-1,
            n_jobs=-1,
        )
        model.fit(
            x,
            np.log1p(family_train[TARGET].clip(lower=0)),
            categorical_feature=CATEGORICALS,
        )
        for name, gain in zip(FEATURES, model.feature_importances_, strict=True):
            importance[name] += float(gain)

        histories = {
            sid: group.sort_values(DATE)[TARGET].astype(float).clip(lower=0).tolist()
            for sid, group in recent[recent["family"] == family].groupby(SERIES_ID)
        }
        family_predictions: list[pd.DataFrame] = []
        for date in sorted(family_future[DATE].unique()):
            day = family_future[family_future[DATE] == date].copy()
            rows = [
                _future_features(row, histories.get(str(row[SERIES_ID]), []))
                for _, row in day.iterrows()
            ]
            day_x = pd.DataFrame(rows, index=day.index)[FEATURES]
            for column in CATEGORICALS:
                day_x[column] = pd.Categorical(day_x[column], categories=categories[column])
            day["pred"] = np.clip(np.expm1(model.predict(day_x)), 0, None)
            for sid, pred in zip(day[SERIES_ID], day["pred"], strict=True):
                histories.setdefault(str(sid), []).append(float(pred))
            family_predictions.append(day[OUTPUT])
        predictions.append(pd.concat(family_predictions, ignore_index=True))

    if not predictions:
        raise ValueError("再帰予測を作れるファミリーがありません")
    result = pd.concat(predictions, ignore_index=True)
    if len(result) != len(future):
        missing = set(future[ROW_ID]) - set(result[ROW_ID])
        raise ValueError(f"再帰予測に不足行があります: {len(missing)}")
    ranked: list[dict[str, float | str]] = [
        {"feature": name, "gain": gain}
        for name, gain in sorted(importance.items(), key=lambda item: -item[1])
    ]
    return result[OUTPUT], ranked
