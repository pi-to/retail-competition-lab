"""Amazon Chronos-2。系列の形と、未来に分かる共変量をゼロショットで読む。"""

from __future__ import annotations

import gc
from typing import Any

import pandas as pd

from retail_lab import DATE, ROW_ID, SERIES_ID, TARGET

CHECKPOINT = "amazon/chronos-2"
ORG = "Amazon"
OUTPUT_COLUMNS = [ROW_ID, DATE, SERIES_ID, "pred"]


def load_pipeline(checkpoint: str = CHECKPOINT, device: str = "cpu") -> Any:
    from chronos import Chronos2Pipeline

    return Chronos2Pipeline.from_pretrained(checkpoint, device_map=device)


def forecast(
    history: pd.DataFrame,
    future: pd.DataFrame,
    horizon: int,
    covariates: list[str],
    pipe: Any | None = None,
    batch_size: int = 8,
) -> pd.DataFrame:
    """``covariates`` は未来側でも値が分かる列だけを渡す。"""
    owned = pipe is None
    if pipe is None:
        pipe = load_pipeline()

    context = history[[SERIES_ID, DATE, TARGET, *covariates]].rename(
        columns={SERIES_ID: "id", DATE: "timestamp", TARGET: "target"}
    )
    future_frame = future[[SERIES_ID, DATE, *covariates]].rename(
        columns={SERIES_ID: "id", DATE: "timestamp"}
    )
    predictions = pipe.predict_df(
        context.sort_values(["id", "timestamp"]),
        future_df=future_frame.sort_values(["id", "timestamp"]),
        prediction_length=horizon,
        quantile_levels=[0.5],
        id_column="id",
        timestamp_column="timestamp",
        target="target",
        batch_size=batch_size,
    )
    if owned:
        del pipe
        gc.collect()

    predictions = predictions.rename(
        columns={"id": SERIES_ID, "timestamp": DATE, "predictions": "pred"}
    )
    predictions[DATE] = pd.to_datetime(predictions[DATE])
    predictions["pred"] = predictions["pred"].clip(lower=0)
    out = future[[ROW_ID, DATE, SERIES_ID]].merge(
        predictions[[SERIES_ID, DATE, "pred"]], on=[SERIES_ID, DATE], how="left"
    )
    out["pred"] = out["pred"].fillna(0.0)
    return out[OUTPUT_COLUMNS]
