"""RMSLE. コンペ公式と同じ log1p の RMSE。"""

from __future__ import annotations

import numpy as np
import pandas as pd


def rmsle(y_true: np.ndarray | pd.Series, y_pred: np.ndarray | pd.Series) -> float:
    yt = np.asarray(y_true, dtype=np.float64)
    yp = np.clip(np.asarray(y_pred, dtype=np.float64), 0.0, None)
    return float(np.sqrt(np.mean((np.log1p(yp) - np.log1p(np.maximum(yt, 0.0))) ** 2)))


def business_metrics(y_true: np.ndarray | pd.Series, y_pred: np.ndarray | pd.Series) -> dict:
    """非エンジニアに説明できる指標。個数ベースで読む。"""
    yt = np.maximum(np.asarray(y_true, dtype=np.float64), 0.0)
    yp = np.clip(np.asarray(y_pred, dtype=np.float64), 0.0, None)
    total = yt.sum()
    return {
        # 合計に対して何%ずれたか（プラスマイナスを打ち消さない）
        "wape": float(np.abs(yp - yt).sum() / total) if total > 0 else float("nan"),
        # 多めに見たか少なめに見たか
        "bias": float((yp.sum() - total) / total) if total > 0 else float("nan"),
        # 実績より少なく見た割合。欠品側に外したケース
        "under_rate": float((yp < yt).mean()),
        "mae": float(np.abs(yp - yt).mean()),
    }
