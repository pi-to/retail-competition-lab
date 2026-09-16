"""RMSLE. コンペ公式と同じ log1p の RMSE。"""

from __future__ import annotations

import numpy as np
import pandas as pd


def rmsle(y_true: np.ndarray | pd.Series, y_pred: np.ndarray | pd.Series) -> float:
    yt = np.asarray(y_true, dtype=np.float64)
    yp = np.clip(np.asarray(y_pred, dtype=np.float64), 0.0, None)
    return float(np.sqrt(np.mean((np.log1p(yp) - np.log1p(np.maximum(yt, 0.0))) ** 2)))
