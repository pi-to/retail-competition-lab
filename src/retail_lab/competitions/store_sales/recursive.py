"""商品ファミリー別 LightGBM を1日ずつ前へ進める再帰予測。

1日目の予測を履歴へ足し、2日目ではそれを `lag_1` として使う。
これで16日一括予測では使えなかった直近1・7・14日の週次リズムを安全に使える。
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier, LGBMRegressor

from retail_lab import DATE, ROW_ID, SERIES_ID, TARGET

LAGS = (1, 7, 14, 16, 21, 28, 35, 42, 49, 56, 63)
ROLLS = (7, 14, 28)
BASE_FEATURES = [
    "onpromotion",
    "promo_log",
    "promo_lag_1",
    "promo_lag_7",
    "promo_lead_1",
    "promo_lead_7",
    "promo_roll_7",
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
    "is_regional_holiday",
    "is_holiday_eve",
    "days_to_holiday",
    "days_after_holiday",
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

# 売れない日が多い系統と、水準が動く系統向けの追加特徴。
# どれも「その日より前の売上」だけから作るので、再帰予測でも同じ式で計算できる。
SALE_THRESHOLD = 0.5
SALE_GAP_CAP = 56
ZERO_WINDOW = 28
LEVEL_WINDOW = 112
INTERMITTENT_FEATURES = [
    "recursive_days_since_sale",
    "recursive_zero_rate_28",
    "recursive_sale_mean_28",
    "recursive_level_ratio",
    "recursive_dow_mean_4",
]
INTERMITTENT_ALL = [*FEATURES, *INTERMITTENT_FEATURES]


def _days_since_sale(values: np.ndarray) -> np.ndarray:
    """その日より前に最後に売れてから何日か。売れていなければ上限。"""
    out = np.empty(len(values), dtype=float)
    gap = float(SALE_GAP_CAP)
    for i, value in enumerate(values):
        out[i] = gap
        gap = 1.0 if value >= SALE_THRESHOLD else min(gap + 1.0, float(SALE_GAP_CAP))
    return out


def _days_since_sale_of_history(values: list[float]) -> float:
    recent = values[-SALE_GAP_CAP:]
    for back, value in enumerate(reversed(recent), start=1):
        if value >= SALE_THRESHOLD:
            return float(back)
    return float(SALE_GAP_CAP)


def _training_features(frame: pd.DataFrame, intermittent: bool = False) -> pd.DataFrame:
    out = frame.sort_values([SERIES_ID, DATE]).copy()
    grouped = out.groupby(SERIES_ID, sort=False)[TARGET]
    for lag in LAGS:
        out[f"recursive_lag_{lag}"] = grouped.shift(lag)
    shifted = grouped.shift(1)
    for window in ROLLS:
        out[f"recursive_roll_{window}"] = shifted.groupby(out[SERIES_ID]).transform(
            lambda series, size=window: series.rolling(size, min_periods=size).mean()
        )
    if not intermittent:
        return out

    series_key = out[SERIES_ID]
    sold = (shifted >= SALE_THRESHOLD).astype(float)
    out["recursive_zero_rate_28"] = 1.0 - sold.groupby(series_key).transform(
        lambda s: s.rolling(ZERO_WINDOW, min_periods=ZERO_WINDOW).mean()
    )
    sale_values = shifted.where(shifted >= SALE_THRESHOLD)
    sale_sum = sale_values.groupby(series_key).transform(
        lambda s: s.rolling(ZERO_WINDOW, min_periods=1).sum()
    )
    sale_count = sale_values.groupby(series_key).transform(
        lambda s: s.rolling(ZERO_WINDOW, min_periods=1).count()
    )
    out["recursive_sale_mean_28"] = np.where(sale_count > 0, sale_sum / sale_count, 0.0)
    near = shifted.groupby(series_key).transform(
        lambda s: s.rolling(ZERO_WINDOW, min_periods=ZERO_WINDOW).mean()
    )
    far = shifted.groupby(series_key).transform(
        lambda s: s.rolling(LEVEL_WINDOW, min_periods=ZERO_WINDOW).mean()
    )
    out["recursive_level_ratio"] = (near + 1.0) / (far + 1.0)
    out["recursive_dow_mean_4"] = out[
        ["recursive_lag_7", "recursive_lag_14", "recursive_lag_21", "recursive_lag_28"]
    ].mean(axis=1)
    out["recursive_days_since_sale"] = grouped.transform(
        lambda s: pd.Series(_days_since_sale(s.to_numpy(dtype=float)), index=s.index)
    )
    return out


def _intermittent_of_history(values: list[float]) -> dict[str, float]:
    recent = np.asarray(values[-ZERO_WINDOW:], dtype=float)
    far = np.asarray(values[-LEVEL_WINDOW:], dtype=float)
    zero_rate = float((recent < SALE_THRESHOLD).mean()) if len(recent) >= ZERO_WINDOW else np.nan
    sales = recent[recent >= SALE_THRESHOLD]
    near_mean = float(recent.mean()) if len(recent) >= ZERO_WINDOW else np.nan
    far_mean = float(far.mean()) if len(far) >= ZERO_WINDOW else np.nan
    weekday = [values[-lag] for lag in (7, 14, 21, 28) if len(values) >= lag]
    return {
        "recursive_days_since_sale": _days_since_sale_of_history(values),
        "recursive_zero_rate_28": zero_rate,
        "recursive_sale_mean_28": float(sales.mean()) if sales.size else 0.0,
        "recursive_level_ratio": (near_mean + 1.0) / (far_mean + 1.0)
        if np.isfinite(near_mean) and np.isfinite(far_mean)
        else np.nan,
        "recursive_dow_mean_4": float(np.mean(weekday)) if weekday else np.nan,
    }


def _future_features(
    row: pd.Series, values: list[float], intermittent: bool = False
) -> dict[str, Any]:
    features = {name: row[name] for name in BASE_FEATURES}
    for lag in LAGS:
        features[f"recursive_lag_{lag}"] = values[-lag] if len(values) >= lag else np.nan
    for window in ROLLS:
        features[f"recursive_roll_{window}"] = (
            float(np.mean(values[-window:])) if len(values) >= window else np.nan
        )
    if intermittent:
        features.update(_intermittent_of_history(values))
    return features


def fit_predict(
    train: pd.DataFrame,
    future: pd.DataFrame,
    *,
    n_estimators: int = 320,
    context_days: int = 730,
    drop_earthquake: bool = False,
    objective: str = "regression",
    tweedie_variance_power: float = 1.2,
    intermittent: bool = False,
    learning_rate: float = 0.045,
    num_leaves: int = 31,
    hurdle: bool = False,
) -> tuple[pd.DataFrame, list[dict[str, float | str]]]:
    """ファミリーごとに学習し、未来を日ごとに再帰予測する。

    `future[TARGET]` は一切読まない。検証時に答えが同じDataFrame内にあっても漏洩しない。
    `objective="tweedie"` はゼロが多い系統向け。予測は非負のまま出す。
    `intermittent=True` は売れない日の続き方と水準の動きを特徴に足す。
    `hurdle=True` は「売れるか」と「売れたらいくらか」を別に学び、掛けて戻す。
    """
    if objective not in {"regression", "tweedie"}:
        raise ValueError(f"未対応の objective です: {objective}")
    if hurdle and objective != "regression":
        raise ValueError("hurdle は log1p 回帰のときだけ使えます")
    columns = INTERMITTENT_ALL if intermittent else FEATURES
    cutoff = train[DATE].max() - pd.Timedelta(days=context_days)
    recent = train[train[DATE] > cutoff]
    if drop_earthquake and "is_earthquake" in recent.columns:
        recent = recent[recent["is_earthquake"] == 0]
    featured = _training_features(recent, intermittent=intermittent)
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

        x = family_train[columns].copy()
        categories: dict[str, pd.Index] = {}
        for column in CATEGORICALS:
            x[column] = x[column].astype("category")
            categories[column] = x[column].cat.categories

        params: dict[str, Any] = {
            "n_estimators": n_estimators,
            "learning_rate": learning_rate,
            "num_leaves": num_leaves,
            "max_depth": -1,
            "min_child_samples": 30,
            "subsample": 0.85,
            "colsample_bytree": 0.85,
            "reg_lambda": 0.5,
            "random_state": 42,
            "verbose": -1,
            "n_jobs": -1,
        }
        if objective == "tweedie":
            params["objective"] = "tweedie"
            params["tweedie_variance_power"] = tweedie_variance_power
            target = family_train[TARGET].clip(lower=0)
        else:
            target = np.log1p(family_train[TARGET].clip(lower=0))

        model = LGBMRegressor(**params)
        gate: LGBMClassifier | None = None
        if hurdle:
            sold = (family_train[TARGET] >= SALE_THRESHOLD).to_numpy()
            if sold.any() and not sold.all():
                gate = LGBMClassifier(**params)
                gate.fit(x, sold.astype(int), categorical_feature=CATEGORICALS)
                # 売れた日だけで「売れたらいくらか」を学ぶ
                model.fit(
                    x[sold],
                    np.log1p(family_train.loc[sold, TARGET].clip(lower=0)),
                    categorical_feature=CATEGORICALS,
                )
            else:
                model.fit(x, target, categorical_feature=CATEGORICALS)
        else:
            model.fit(x, target, categorical_feature=CATEGORICALS)
        for name, gain in zip(columns, model.feature_importances_, strict=True):
            importance[name] += float(gain)

        histories = {
            sid: group.sort_values(DATE)[TARGET].astype(float).clip(lower=0).tolist()
            for sid, group in recent[recent["family"] == family].groupby(SERIES_ID)
        }
        family_predictions: list[pd.DataFrame] = []
        for date in sorted(family_future[DATE].unique()):
            day = family_future[family_future[DATE] == date].copy()
            rows = [
                _future_features(
                    row, histories.get(str(row[SERIES_ID]), []), intermittent=intermittent
                )
                for _, row in day.iterrows()
            ]
            day_x = pd.DataFrame(rows, index=day.index)[columns]
            for column in CATEGORICALS:
                day_x[column] = pd.Categorical(day_x[column], categories=categories[column])
            raw = model.predict(day_x)
            if gate is not None:
                # RMSLE が最適になるのは expm1(log1p売上の期待値)。
                # 売れない日の log1p は0なので、売れる確率をそのまま掛ければよい。
                chance = gate.predict_proba(day_x)[:, 1]
                day["pred"] = np.clip(np.expm1(chance * np.clip(raw, 0, None)), 0, None)
            else:
                day["pred"] = np.clip(raw if objective == "tweedie" else np.expm1(raw), 0, None)
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
