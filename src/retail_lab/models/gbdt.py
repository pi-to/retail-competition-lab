"""LightGBM。系列を横断して、プロモや祝日の効果を学ぶ担当。"""

from __future__ import annotations

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor

from retail_lab import DATE, ROW_ID, SERIES_ID, TARGET

OUTPUT_COLUMNS = [ROW_ID, DATE, SERIES_ID, "pred"]


def fit_predict(
    train: pd.DataFrame,
    future: pd.DataFrame,
    features: list[str],
    categoricals: list[str],
    n_estimators: int = 400,
) -> tuple[pd.DataFrame, list[dict[str, float | str]]]:
    """log1p(target) を学習して、未来の行に対する予測と特徴の使われ方を返す。"""
    labeled = train[train[TARGET].notna()].copy()
    x = labeled[features].copy()
    y = np.log1p(labeled[TARGET].clip(lower=0))
    categories = {}
    for column in categoricals:
        x[column] = x[column].astype("category")
        categories[column] = x[column].cat.categories

    model = LGBMRegressor(
        n_estimators=n_estimators,
        learning_rate=0.05,
        num_leaves=31,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_samples=20,
        random_state=42,
        verbose=-1,
    )
    model.fit(x, y, categorical_feature=categoricals)

    need = future.copy()
    for column in categoricals:
        need[column] = pd.Categorical(need[column], categories=categories[column])
    need["pred"] = np.clip(np.expm1(model.predict(need[features])), 0, None)

    importance: list[dict[str, float | str]] = [
        {"feature": name, "gain": float(gain)}
        for name, gain in sorted(
            zip(features, model.feature_importances_, strict=True),
            key=lambda pair: -pair[1],
        )
    ]
    return need[OUTPUT_COLUMNS], importance
