"""店を横断して学ぶ表モデル。プロモと祝日の効果をここで取る。"""

from __future__ import annotations

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor

from features import CAT_FEATURES, LGBM_FEATURES, add_lag_features, attach_static


def _panel(train: pd.DataFrame, future: pd.DataFrame, stores, oil, holidays) -> pd.DataFrame:
    hist = attach_static(train, stores, oil, holidays)
    fut = attach_static(future, stores, oil, holidays)
    if "sales" not in fut.columns:
        fut["sales"] = np.nan
    panel = pd.concat([hist, fut], ignore_index=True)
    return add_lag_features(panel)


def fit_predict(
    train: pd.DataFrame,
    future: pd.DataFrame,
    stores: pd.DataFrame,
    oil: pd.DataFrame,
    holidays: pd.DataFrame,
) -> tuple[pd.DataFrame, list[dict]]:
    panel = _panel(train, future, stores, oil, holidays)
    train_ids = set(train["id"].tolist())
    future_ids = set(future["id"].tolist())
    labeled = panel[panel["id"].isin(train_ids) & panel["lag_16"].notna()].copy()
    X = labeled[LGBM_FEATURES].copy()
    y = np.log1p(labeled["sales"].clip(lower=0))
    for c in CAT_FEATURES:
        X[c] = X[c].astype("category")
        panel[c] = pd.Categorical(panel[c], categories=X[c].cat.categories)

    model = LGBMRegressor(
        n_estimators=400,
        learning_rate=0.05,
        num_leaves=31,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_samples=20,
        random_state=42,
        verbose=-1,
    )
    model.fit(X, y, categorical_feature=CAT_FEATURES)

    need = panel[panel["id"].isin(future_ids)].copy()
    for c in CAT_FEATURES:
        need[c] = pd.Categorical(need[c], categories=X[c].cat.categories)
    pred_log = model.predict(need[LGBM_FEATURES])
    need["pred"] = np.clip(np.expm1(pred_log), 0, None)

    importance = [
        {"feature": f, "gain": float(g)}
        for f, g in sorted(
            zip(LGBM_FEATURES, model.feature_importances_),
            key=lambda x: -x[1],
        )
    ]
    cols = ["id", "date", "series_id", "store_nbr", "family", "pred"]
    return need[cols], importance
