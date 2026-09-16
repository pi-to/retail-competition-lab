"""Google TimesFM 2.5。AWS に依存しない対照。数量の並びだけを読む。"""

from __future__ import annotations

import gc
from typing import Any

import numpy as np
import pandas as pd

from retail_lab import DATE, ROW_ID, SERIES_ID, TARGET

CHECKPOINT = "google/timesfm-2.5-200m-pytorch"
ORG = "Google"
CONTEXT = 512
OUTPUT_COLUMNS = [ROW_ID, DATE, SERIES_ID, "pred"]


def load_model(checkpoint: str = CHECKPOINT, max_horizon: int = 32) -> Any:
    import timesfm

    model = timesfm.TimesFM_2p5_200M_torch.from_pretrained(checkpoint)
    model.compile(
        timesfm.ForecastConfig(
            max_context=CONTEXT,
            max_horizon=max_horizon,
            normalize_inputs=True,
            infer_is_positive=True,
            per_core_batch_size=8,
        )
    )
    return model


def forecast(
    history: pd.DataFrame,
    future: pd.DataFrame,
    horizon: int,
    model: Any | None = None,
) -> pd.DataFrame:
    hist = history.sort_values([SERIES_ID, DATE])
    fut = future.sort_values([SERIES_ID, DATE])
    series_ids = list(dict.fromkeys(fut[SERIES_ID].tolist()))

    by_series = {sid: group for sid, group in hist.groupby(SERIES_ID)[TARGET]}
    inputs: list[np.ndarray] = []
    for sid in series_ids:
        values = (
            by_series.get(sid, pd.Series(dtype="float64")).astype(float).clip(lower=0).to_numpy()
        )
        if len(values) > CONTEXT:
            values = values[-CONTEXT:]
        if len(values) < 8:
            values = np.pad(values, (8 - len(values), 0))
        inputs.append(values.astype(np.float32))

    owned = model is None
    if model is None:
        model = load_model(max_horizon=max(32, horizon))
    point, _quantiles = model.forecast(horizon=horizon, inputs=inputs)
    if owned:
        del model
        gc.collect()

    frames: list[pd.DataFrame] = []
    for index, sid in enumerate(series_ids):
        sub = fut[fut[SERIES_ID] == sid][[ROW_ID, DATE, SERIES_ID]].copy()
        sub["pred"] = np.clip(point[index, : len(sub)], 0, None)
        frames.append(sub)
    return pd.concat(frames, ignore_index=True)[OUTPUT_COLUMNS]
