import numpy as np
from metrics import business_metrics, rmsle


def test_rmsle_zero():
    y = np.array([0.0, 1.0, 10.0])
    assert rmsle(y, y) == 0.0


def test_rmsle_clips_negative_predictions():
    y = np.array([1.0, 3.0])
    p = np.array([-1.0, 3.0])
    assert rmsle(y, p) > 0


def test_rmsle_punishes_relative_error_not_absolute():
    """少量商品を2倍に外す方が、主力を1割外すより重い。"""
    small = rmsle(np.array([3.0]), np.array([6.0]))
    large = rmsle(np.array([3000.0]), np.array([3300.0]))
    assert small > large


def test_business_metrics_perfect_forecast():
    y = np.array([0.0, 5.0, 10.0])
    m = business_metrics(y, y)
    assert m["wape"] == 0.0
    assert m["bias"] == 0.0
    assert m["under_rate"] == 0.0


def test_business_metrics_direction():
    y = np.array([10.0, 10.0])
    over = business_metrics(y, np.array([12.0, 12.0]))
    under = business_metrics(y, np.array([8.0, 8.0]))
    assert over["bias"] > 0
    assert under["bias"] < 0
    assert under["under_rate"] == 1.0
    assert over["wape"] == under["wape"]
