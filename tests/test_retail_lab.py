from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from retail_lab import blending, registry
from retail_lab.competition import CompetitionSpec
from retail_lab.metrics import business_metrics, rmsle
from retail_lab.models import naive
from retail_lab.validation import split_panel


def _panel(days: int = 40, horizon: int = 4) -> pd.DataFrame:
    dates = pd.date_range("2017-01-01", periods=days + horizon)
    rows = []
    row_id = 0
    for series in ("1::A", "2::B"):
        for i, date in enumerate(dates):
            rows.append(
                {
                    "row_id": row_id,
                    "series_id": series,
                    "date": date,
                    "target": float(10 + i % 7) if i < days else np.nan,
                }
            )
            row_id += 1
    return pd.DataFrame(rows)


def test_rmsle_zero():
    y = np.array([0.0, 1.0, 10.0])
    assert rmsle(y, y) == 0.0


def test_rmsle_clips_negative_predictions():
    assert rmsle(np.array([1.0, 3.0]), np.array([-1.0, 3.0])) > 0


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


def test_split_panel_holds_out_the_last_horizon_days():
    horizon = 4
    split = split_panel(_panel(horizon=horizon), horizon)
    assert split.val["date"].nunique() == horizon
    assert split.train["date"].max() < split.val["date"].min()
    assert split.future["target"].isna().all()
    assert len(split.labeled) == len(split.train) + len(split.val)


def test_seasonal_naive_covers_every_future_row():
    horizon = 4
    panel = _panel(horizon=horizon)
    split = split_panel(panel, horizon)
    pred = naive.seasonal_naive(split.train, split.val)
    assert len(pred) == len(split.val)
    assert pred["pred"].notna().all()
    assert (pred["pred"] >= 0).all()


def test_inverse_rmsle_weights_favor_the_better_model():
    weights = blending.inverse_rmsle_weights({"good": 0.2, "bad": 0.4})
    assert weights["good"] > weights["bad"]
    assert pytest.approx(sum(weights.values()), abs=1e-9) == 1.0


def test_inverse_rmsle_weights_ignore_unusable_scores():
    assert blending.inverse_rmsle_weights({"broken": float("nan"), "zero": 0.0}) == {}


def test_fitted_weights_favor_the_model_that_matches_the_truth():
    """当たっているモデルに重みが寄る。log 空間の非負最小二乗なので解は一意。"""
    truth = pd.DataFrame({"row_id": [1, 2, 3, 4], "target": [10.0, 20.0, 30.0, 40.0]})
    preds = {
        "good": pd.DataFrame({"row_id": [1, 2, 3, 4], "pred": [10.0, 20.0, 30.0, 40.0]}),
        "bad": pd.DataFrame({"row_id": [1, 2, 3, 4], "pred": [1.0, 1.0, 1.0, 1.0]}),
    }
    weights = blending.fit_log_weights(preds, truth)
    assert weights["good"] > weights.get("bad", 0.0)


def test_fitted_blend_is_never_worse_than_the_best_single_model():
    """単体は重みの空間に含まれるので、当てはめた混合が検証窓で負けることはない。"""
    truth = pd.DataFrame({"row_id": [1, 2, 3, 4], "target": [10.0, 20.0, 30.0, 40.0]})
    preds = {
        "close": pd.DataFrame({"row_id": [1, 2, 3, 4], "pred": [11.0, 19.0, 33.0, 37.0]}),
        "off": pd.DataFrame({"row_id": [1, 2, 3, 4], "pred": [2.0, 40.0, 5.0, 90.0]}),
    }
    singles = {name: blending.score_against(frame, truth) for name, frame in preds.items()}
    fitted = blending.blend(preds, blending.fit_log_weights(preds, truth))
    assert blending.score_against(fitted, truth) <= min(singles.values()) + 1e-9


def test_log_blend_of_identical_predictions_is_unchanged():
    preds = {
        "a": pd.DataFrame({"row_id": [1, 2], "series_id": ["s", "s"], "pred": [4.0, 9.0]}),
        "b": pd.DataFrame({"row_id": [1, 2], "series_id": ["s", "s"], "pred": [4.0, 9.0]}),
    }
    out = blending.blend(preds, {"a": 0.5, "b": 0.5})
    assert out["pred"].tolist() == pytest.approx([4.0, 9.0])


def test_zero_out_dead_series_silences_discontinued_items():
    history = pd.DataFrame(
        {
            "series_id": ["dead"] * 3 + ["alive"] * 3,
            "date": list(pd.date_range("2017-01-01", periods=3)) * 2,
            "target": [0.0, 0.0, 0.0, 5.0, 6.0, 7.0],
        }
    )
    pred = pd.DataFrame({"row_id": [1, 2], "series_id": ["dead", "alive"], "pred": [4.0, 4.0]})
    out = blending.zero_out_dead_series(history, pred, lookback=7).set_index("series_id")
    assert out.loc["dead", "pred"] == 0.0
    assert out.loc["alive", "pred"] == 4.0


def test_registry_exposes_specs_with_matching_slugs():
    specs = registry.specs()
    assert specs, "コンペが1つも登録されていない"
    for spec in specs:
        assert isinstance(spec, CompetitionSpec)
        assert registry.spec(spec.slug) is spec
        assert spec.horizon > 0
        assert spec.required_files


def test_registry_rejects_unknown_slug():
    with pytest.raises(KeyError):
        registry.get("no-such-competition")


def test_demo_data_matches_the_official_column_names(tmp_path: Path):
    from retail_lab.competitions.store_sales.demo import generate_demo

    generate_demo(tmp_path)
    train = pd.read_csv(tmp_path / "train.csv")
    test = pd.read_csv(tmp_path / "test.csv")
    assert list(train.columns) == ["id", "date", "store_nbr", "family", "onpromotion", "sales"]
    assert list(test.columns) == ["id", "date", "store_nbr", "family", "onpromotion"]
    assert test["date"].nunique() == 16
    assert set(train["id"]).isdisjoint(set(test["id"]))
