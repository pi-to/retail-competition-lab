"""Google TimesFM 2.5。AWS に依存しない単変量基盤モデル。売上の形だけを読む。"""

from __future__ import annotations

import gc

import numpy as np
import pandas as pd

from data import add_series_id

CHECKPOINT = "google/timesfm-2.5-200m-pytorch"
CONTEXT = 512


def load_model():
    import timesfm

    model = timesfm.TimesFM_2p5_200M_torch.from_pretrained(CHECKPOINT)
    model.compile(
        timesfm.ForecastConfig(
            max_context=CONTEXT,
            max_horizon=32,
            normalize_inputs=True,
            infer_is_positive=True,
            per_core_batch_size=8,
        )
    )
    return model


def forecast(history: pd.DataFrame, future: pd.DataFrame, horizon: int, model=None) -> pd.DataFrame:
    hist = add_series_id(history).sort_values(["series_id", "date"])
    fut = add_series_id(future).sort_values(["series_id", "date"])
    ids = list(dict.fromkeys(fut["series_id"].tolist()))
    inputs: list[np.ndarray] = []
    for sid in ids:
        values = hist.loc[hist["series_id"] == sid, "sales"].astype(float).clip(lower=0).to_numpy()
        if len(values) > CONTEXT:
            values = values[-CONTEXT:]
        if len(values) < 8:
            values = np.pad(values, (8 - len(values), 0))
        inputs.append(values.astype(np.float32))

    owned = model is None
    if model is None:
        model = load_model()
    point, _quantiles = model.forecast(horizon=horizon, inputs=inputs)
    if owned:
        del model
        gc.collect()

    rows: list[dict] = []
    for i, sid in enumerate(ids):
        sub = fut[fut["series_id"] == sid]
        for j, (_, r) in enumerate(sub.iterrows()):
            rows.append(
                {
                    "id": r["id"],
                    "date": r["date"],
                    "series_id": sid,
                    "store_nbr": r["store_nbr"],
                    "family": r["family"],
                    "pred": float(max(point[i, j], 0.0)),
                }
            )
    return pd.DataFrame(rows)
