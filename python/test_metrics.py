import numpy as np
from metrics import rmsle


def test_rmsle_zero():
    y = np.array([0.0, 1.0, 10.0])
    assert rmsle(y, y) == 0.0


def test_rmsle_positive_pred():
    y = np.array([1.0, 3.0])
    p = np.array([-1.0, 3.0])
    assert rmsle(y, p) > 0
