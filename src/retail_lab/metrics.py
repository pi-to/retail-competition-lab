"""指標。順位を決める RMSLE と、現場に説明するための指標を分けて持つ。"""

from __future__ import annotations

import numpy as np
import pandas as pd

FloatArray = np.ndarray


def _clean(
    y_true: FloatArray | pd.Series, y_pred: FloatArray | pd.Series
) -> tuple[FloatArray, FloatArray]:
    yt = np.maximum(np.asarray(y_true, dtype=np.float64), 0.0)
    yp = np.clip(np.asarray(y_pred, dtype=np.float64), 0.0, None)
    return yt, yp


def rmsle(y_true: FloatArray | pd.Series, y_pred: FloatArray | pd.Series) -> float:
    """コンペ公式の指標。log1p に直してからの二乗平均平方根誤差。"""
    yt, yp = _clean(y_true, y_pred)
    return float(np.sqrt(np.mean((np.log1p(yp) - np.log1p(yt)) ** 2)))


def business_metrics(
    y_true: FloatArray | pd.Series, y_pred: FloatArray | pd.Series
) -> dict[str, float]:
    """非エンジニアに説明できる指標。数量ベースで読む。"""
    yt, yp = _clean(y_true, y_pred)
    total = float(yt.sum())
    return {
        # 合計に対して何%ずれたか（プラスマイナスを打ち消さない）
        "wape": float(np.abs(yp - yt).sum() / total) if total > 0 else float("nan"),
        # 多めに見たか少なめに見たか
        "bias": float((yp.sum() - total) / total) if total > 0 else float("nan"),
        # 実績より少なく見た割合。欠品側に外したケース
        "under_rate": float((yp < yt).mean()),
        "mae": float(np.abs(yp - yt).mean()),
    }
