"""Amazon Chronos-2。系列の形 + 未来に分かる共変量（プロモ・祝日・原油）。"""

from __future__ import annotations

import gc

import pandas as pd

from data import add_series_id
from features import attach_static

CHECKPOINT = "amazon/chronos-2"


def _frames(history: pd.DataFrame, future: pd.DataFrame, stores, oil, holidays) -> tuple[pd.DataFrame, pd.DataFrame]:
    hist = attach_static(history, stores, oil, holidays)
    fut = attach_static(future, stores, oil, holidays)
    ctx = pd.DataFrame(
        {
            "id": hist["series_id"],
            "timestamp": hist["date"],
            "target": hist["sales"].astype(float).clip(lower=0),
            "onpromotion": hist["onpromotion"].fillna(0).astype(float),
            "oil": hist["oil"].astype(float),
            "is_national_holiday": hist["is_national_holiday"].astype(float),
            "is_payday": hist["is_payday"].astype(float),
        }
    )
    fut_df = pd.DataFrame(
        {
            "id": fut["series_id"],
            "timestamp": fut["date"],
            "onpromotion": fut["onpromotion"].fillna(0).astype(float),
            "oil": fut["oil"].astype(float),
            "is_national_holiday": fut["is_national_holiday"].astype(float),
            "is_payday": fut["is_payday"].astype(float),
        }
    )
    return ctx.sort_values(["id", "timestamp"]), fut_df.sort_values(["id", "timestamp"])


def forecast(
    history: pd.DataFrame,
    future: pd.DataFrame,
    stores: pd.DataFrame,
    oil: pd.DataFrame,
    holidays: pd.DataFrame,
    horizon: int,
    pipe=None,
) -> pd.DataFrame:
    from chronos import Chronos2Pipeline

    ctx, fut_df = _frames(history, future, stores, oil, holidays)
    owned = pipe is None
    if pipe is None:
        pipe = Chronos2Pipeline.from_pretrained(CHECKPOINT, device_map="cpu")
    pred = pipe.predict_df(
        ctx,
        future_df=fut_df,
        prediction_length=horizon,
        quantile_levels=[0.5],
        id_column="id",
        timestamp_column="timestamp",
        target="target",
        batch_size=8,
    )
    if owned:
        del pipe
        gc.collect()

    pred = pred.rename(columns={"id": "series_id", "timestamp": "date", "predictions": "pred"})
    pred["date"] = pd.to_datetime(pred["date"])
    pred["pred"] = pred["pred"].clip(lower=0)
    fut = add_series_id(future)
    out = fut.merge(pred[["series_id", "date", "pred"]], on=["series_id", "date"], how="left")
    out["pred"] = out["pred"].fillna(0.0)
    return out[["id", "date", "series_id", "store_nbr", "family", "pred"]]


def load_pipeline():
    from chronos import Chronos2Pipeline

    return Chronos2Pipeline.from_pretrained(CHECKPOINT, device_map="cpu")
