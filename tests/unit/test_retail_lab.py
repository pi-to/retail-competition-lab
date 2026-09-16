import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from retail_lab import blending, registry
from retail_lab.competition import CompetitionSpec, run_output_dir
from retail_lab.kaggle import (
    SubmissionValidationError,
    auth_header,
    describe_submission,
    explain_api_error,
    readiness_blockers,
    validate_submission,
)
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


def test_grouped_rmsle_lists_the_worst_group_first():
    pred = pd.DataFrame({"row_id": [1, 2, 3, 4], "pred": [1.0, 1.0, 10.0, 10.0]})
    actual = pd.DataFrame(
        {
            "row_id": [1, 2, 3, 4],
            "target": [1.0, 1.0, 1.0, 1.0],
            "family": ["easy", "easy", "hard", "hard"],
        }
    )
    rows = blending.grouped_rmsle(pred, actual, "family")
    assert rows[0]["group"] == "hard"
    assert rows[0]["rmsle"] > rows[1]["rmsle"]


def test_horizon_blend_picks_the_model_that_matches_each_day():
    """1日目に当たるモデルと2日目に当たるモデルを、日ごとに選べる。"""
    truth = pd.DataFrame(
        {
            "row_id": [1, 2, 3, 4],
            "date": pd.to_datetime(["2017-08-16", "2017-08-16", "2017-08-17", "2017-08-17"]),
            "target": [10.0, 20.0, 30.0, 40.0],
        }
    )
    preds = {
        "early": pd.DataFrame(
            {
                "row_id": [1, 2, 3, 4],
                "date": truth["date"],
                "pred": [10.0, 20.0, 1.0, 1.0],
            }
        ),
        "late": pd.DataFrame(
            {
                "row_id": [1, 2, 3, 4],
                "date": truth["date"],
                "pred": [1.0, 1.0, 30.0, 40.0],
            }
        ),
    }
    origin = pd.Timestamp("2017-08-15")
    weights = blending.fit_log_weights_by_horizon(preds, truth, origin)
    blended = blending.blend_by_horizon(preds, weights, origin)
    assert blending.score_against(blended, truth) < blending.score_against(
        blending.blend(preds, blending.fit_log_weights(preds, truth)), truth
    )
    assert blended.sort_values("row_id")["pred"].tolist() == pytest.approx([10.0, 20.0, 30.0, 40.0])


def test_choose_blend_prefers_horizon_weights_when_they_win():
    truth = pd.DataFrame(
        {
            "row_id": [1, 2, 3, 4],
            "date": pd.to_datetime(["2017-08-16", "2017-08-16", "2017-08-17", "2017-08-17"]),
            "target": [10.0, 20.0, 30.0, 40.0],
        }
    )
    preds = {
        "early": pd.DataFrame(
            {
                "row_id": [1, 2, 3, 4],
                "date": truth["date"],
                "pred": [10.0, 20.0, 1.0, 1.0],
            }
        ),
        "late": pd.DataFrame(
            {
                "row_id": [1, 2, 3, 4],
                "date": truth["date"],
                "pred": [1.0, 1.0, 30.0, 40.0],
            }
        ),
    }
    train = pd.DataFrame({"date": pd.to_datetime(["2017-08-15"])})
    choice = blending.choose_blend(preds, preds, train, truth, truth)
    assert choice["strategy"] == "fitted_horizon"
    assert choice["score"] < blending.score_against(
        blending.blend(preds, blending.fit_log_weights(preds, truth)), truth
    )


def test_choose_blend_prefers_family_weights_when_they_win():
    """Aが当たる系統とBが当たる系統を、ファミリーごとに選べる。"""
    truth = pd.DataFrame(
        {
            "row_id": [1, 2, 3, 4],
            "date": pd.to_datetime(["2017-08-16"] * 4),
            "target": [10.0, 20.0, 30.0, 40.0],
        }
    )
    preds = {
        "a": pd.DataFrame(
            {
                "row_id": [1, 2, 3, 4],
                "date": truth["date"],
                "series_id": ["1::HARD", "1::HARD", "2::EASY", "2::EASY"],
                "pred": [10.0, 20.0, 1.0, 1.0],
            }
        ),
        "b": pd.DataFrame(
            {
                "row_id": [1, 2, 3, 4],
                "date": truth["date"],
                "series_id": ["1::HARD", "1::HARD", "2::EASY", "2::EASY"],
                "pred": [1.0, 1.0, 30.0, 40.0],
            }
        ),
    }
    train = pd.DataFrame({"date": pd.to_datetime(["2017-08-15"])})
    choice = blending.choose_blend(preds, preds, train, truth, truth)
    assert choice["strategy"] == "fitted_family"
    assert choice["score"] < blending.score_against(
        blending.blend(preds, blending.fit_log_weights(preds, truth)), truth
    )


TOY_TRUTH = {"A": 10.0, "B": 40.0, "C": 100.0}
# 1組の重みでは3ファミリーすべてに合わせられない。ファミリー別なら合わせられる。
TOY_PREDS = {"early": {"A": 10.0, "B": 1.0, "C": 5.0}, "late": {"A": 1.0, "B": 40.0, "C": 5.0}}


def _family_panel_preds(noise: float = 0.0) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    """3ファミリー×6店舗の予測。ファミリーごとに当たるモデルが違う。"""
    rows = []
    row_id = 0
    for family, target in TOY_TRUTH.items():
        for store in range(1, 7):
            for day in range(2):
                rows.append(
                    {
                        "row_id": row_id,
                        "series_id": f"{store}::{family}",
                        "date": pd.Timestamp("2017-08-16") + pd.Timedelta(days=day),
                        "target": target,
                    }
                )
                row_id += 1
    truth = pd.DataFrame(rows)
    families = truth["series_id"].str.split("::").str[-1]
    rng = np.random.default_rng(0)
    preds = {}
    for name, by_family in TOY_PREDS.items():
        frame = truth[["row_id", "series_id", "date"]].copy()
        frame["pred"] = families.map(by_family).to_numpy()
        frame["pred"] = frame["pred"] * (1 + noise * rng.standard_normal(len(frame)))
        preds[name] = frame
    return preds, truth


def test_choose_blend_reports_a_holdout_score_from_unseen_series():
    """重みを当てはめた行では選ばない。系列を割って、見ていない側で採点する。"""
    preds, truth = _family_panel_preds(noise=0.05)
    train = pd.DataFrame({"date": pd.to_datetime(["2017-08-15"])})

    choice = blending.choose_blend(preds, preds, train, truth, truth)

    assert choice["strategy"] == "fitted_family"
    assert choice["holdout_score"] is not None
    assert choice["holdout_score"] >= choice["score"]
    assert set(choice["candidates"]) >= {"fitted", "fitted_family"}


def test_choose_blend_drops_a_model_that_only_adds_noise():
    """当てはめには使えるが、見ていない系列では足を引っ張るモデルは外す。"""
    preds, truth = _family_panel_preds(noise=0.05)
    rng = np.random.default_rng(7)
    noise_only = preds["early"].copy()
    noise_only["pred"] = rng.uniform(1, 120, len(noise_only))
    preds["noise"] = noise_only
    train = pd.DataFrame({"date": pd.to_datetime(["2017-08-15"])})

    choice = blending.choose_blend(preds, preds, train, truth, truth)

    assert "noise" not in choice["models_used"]
    assert set(choice["models_used"]) >= {"early", "late"}


def test_series_halves_keep_every_family_on_both_sides():
    preds, _truth = _family_panel_preds()
    fit_ids, hold_ids = blending.series_halves(preds)
    frame = preds["early"]
    families = frame["series_id"].str.split("::").str[-1]
    fit_families = set(families[frame["row_id"].isin(fit_ids)])
    hold_families = set(families[frame["row_id"].isin(hold_ids)])

    assert fit_families == hold_families == set(TOY_TRUTH)
    assert not fit_ids & hold_ids


def test_shrink_weights_pulls_group_weights_toward_the_global_mix():
    shrunk = blending.shrink_weights({"g": {"a": 1.0}}, {"a": 0.5, "b": 0.5}, 0.5)
    assert shrunk["g"]["a"] == pytest.approx(0.75)
    assert shrunk["g"]["b"] == pytest.approx(0.25)


def test_shrink_weights_keeps_the_group_mix_when_alpha_is_one():
    shrunk = blending.shrink_weights({"g": {"a": 1.0}}, {"b": 1.0}, 1.0)
    assert shrunk["g"] == {"a": 1.0}


def test_pool_predictions_min_is_never_above_any_member():
    preds = {
        "a": pd.DataFrame(
            {
                "row_id": [1, 2],
                "date": pd.to_datetime(["2017-08-16", "2017-08-17"]),
                "series_id": ["1::A", "1::A"],
                "pred": [10.0, 4.0],
            }
        ),
        "b": pd.DataFrame(
            {
                "row_id": [1, 2],
                "date": pd.to_datetime(["2017-08-16", "2017-08-17"]),
                "series_id": ["1::A", "1::A"],
                "pred": [3.0, 9.0],
            }
        ),
    }
    pooled = blending.pool_predictions(preds, ["a", "b"], how="min")
    assert pooled.sort_values("row_id")["pred"].tolist() == pytest.approx([3.0, 4.0])


def test_prediction_origin_is_the_day_before_the_first_forecast():
    preds = {
        "m": pd.DataFrame(
            {"date": pd.to_datetime(["2017-08-16", "2017-08-17"]), "row_id": [1, 2], "pred": [1, 1]}
        )
    }
    assert blending.prediction_origin(preds) == pd.Timestamp("2017-08-15")


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


EXOG_DEFAULTS = {
    "is_regional_holiday": 0,
    "is_holiday_eve": 0,
    "days_to_holiday": 14,
    "days_after_holiday": 14,
    "promo_lag_1": 0.0,
    "promo_lag_7": 0.0,
    "promo_lead_1": 0.0,
    "promo_lead_7": 0.0,
    "promo_roll_7": 0.0,
}


def test_demo_data_matches_the_official_column_names(tmp_path: Path):
    from retail_lab.competitions.store_sales.demo import generate_demo

    generate_demo(tmp_path)
    train = pd.read_csv(tmp_path / "train.csv")
    test = pd.read_csv(tmp_path / "test.csv")
    assert list(train.columns) == ["id", "date", "store_nbr", "family", "onpromotion", "sales"]
    assert list(test.columns) == ["id", "date", "store_nbr", "family", "onpromotion"]
    assert test["date"].nunique() == 16
    assert set(train["id"]).isdisjoint(set(test["id"]))


def test_submission_validation_accepts_matching_ids(tmp_path: Path):
    sample = tmp_path / "sample_submission.csv"
    submission = tmp_path / "submission.csv"
    pd.DataFrame({"id": [10, 11, 12], "sales": [0.0, 1.25, 2.5]}).to_csv(sample, index=False)
    pd.DataFrame({"id": [10, 11, 12], "sales": [0.5, 1.0, 2.0]}).to_csv(submission, index=False)

    result = validate_submission(submission, sample)

    assert result["rows"] == 3
    assert result["id_min"] == 10
    assert result["id_max"] == 12
    assert result["sales_min"] == 0.5
    assert result["sales_max"] == 2.0


@pytest.mark.parametrize(
    ("submission_data", "message"),
    [
        ({"id": [10, 11], "sales": [1.0, 2.0]}, "行数"),
        ({"id": [10, 11, 99], "sales": [1.0, 2.0, 3.0]}, "id"),
        ({"id": [10, 11, 12], "sales": [1.0, -1.0, 3.0]}, "負"),
        ({"id": [10, 11, 12], "sales": [1.0, float("nan"), 3.0]}, "欠損"),
    ],
)
def test_submission_validation_rejects_invalid_files(
    tmp_path: Path, submission_data: dict[str, list[float]], message: str
):
    sample = tmp_path / "sample_submission.csv"
    submission = tmp_path / "submission.csv"
    pd.DataFrame({"id": [10, 11, 12], "sales": [0.0, 0.0, 0.0]}).to_csv(sample, index=False)
    pd.DataFrame(submission_data).to_csv(submission, index=False)

    with pytest.raises(SubmissionValidationError, match=message):
        validate_submission(submission, sample)


def test_explain_api_error_points_a_permission_denial_at_joining_the_competition():
    """権限拒否は、トークンではなくコンペ未参加が原因のことが多い。"""
    detail = '{"code":403,"message":"Permission \'competitions.participate\' was denied"}'
    message, hint = explain_api_error(403, detail, "store-sales-time-series-forecasting")
    assert "competitions.participate" in message
    assert "store-sales-time-series-forecasting/rules" in hint
    assert "Join Competition" in hint


def test_explain_api_error_detects_that_the_competition_was_not_joined():
    detail = '{"code":400,"message":"You do not have a Team in this Competition."}'
    message, hint = explain_api_error(400, detail, "store-sales-time-series-forecasting")
    assert "参加" in message
    assert "store-sales-time-series-forecasting/rules" in hint


def test_auth_header_reads_the_env_file_so_a_token_swap_needs_no_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.delenv("KAGGLE_API_TOKEN", raising=False)
    monkeypatch.delenv("KAGGLE_KEY", raising=False)
    monkeypatch.delenv("KAGGLE_USERNAME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".env.local").write_text(
        '# comment\nKAGGLE_API_TOKEN="KGAT_swapped"\n', encoding="utf-8"
    )

    assert auth_header(tmp_path) == {"Authorization": "Bearer KGAT_swapped"}


def test_auth_header_prefers_the_process_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("KAGGLE_API_TOKEN", "KGAT_from_env")
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".env.local").write_text("KAGGLE_API_TOKEN=KGAT_from_file\n", encoding="utf-8")

    assert auth_header(tmp_path) == {"Authorization": "Bearer KGAT_from_env"}


def test_demo_runs_do_not_overwrite_the_official_submission(tmp_path: Path):
    official = run_output_dir(tmp_path, "store-sales", "kaggle")
    demo = run_output_dir(tmp_path, "store-sales", "demo")
    assert official == tmp_path / "outputs" / "store-sales"
    assert demo != official
    assert official in demo.parents


def test_describe_submission_counts_the_header_separately(tmp_path: Path):
    sample = tmp_path / "sample_submission.csv"
    submission = tmp_path / "submission.csv"
    pd.DataFrame({"id": [1, 2, 3], "sales": [0.0, 0.0, 0.0]}).to_csv(sample, index=False)
    pd.DataFrame({"id": [1, 2, 3], "sales": [1.0, 2.0, 3.0]}).to_csv(submission, index=False)

    facts = describe_submission(submission, sample)

    assert facts["valid"] is True
    assert facts["rows"] == 3
    assert facts["lines"] == 4
    assert facts["header"] == "id,sales"


def test_readiness_names_the_account_that_has_not_joined():
    """参加済みかどうかはアカウント単位。誰が参加すべきかまで言う。"""
    info = {"ref": "https://www.kaggle.com/competitions/x", "userHasEntered": False}
    blockers = readiness_blockers("pitodonkey", info, "store-sales-time-series-forecasting")
    assert len(blockers) == 1
    assert "pitodonkey" in blockers[0]
    assert "store-sales-time-series-forecasting/rules" in blockers[0]


def test_readiness_is_silent_when_the_account_can_submit():
    info = {"userHasEntered": True, "submissionsDisabled": False, "isKernelsSubmissionsOnly": False}
    assert readiness_blockers("pitodonkey", info, "store-sales-time-series-forecasting") == []


def test_readiness_reports_notebook_only_competitions():
    info = {"userHasEntered": True, "isKernelsSubmissionsOnly": True}
    blockers = readiness_blockers("pitodonkey", info, "arc-prize")
    assert any("ノートブック" in blocker for blocker in blockers)


def test_explain_api_error_keeps_the_original_message_when_unknown():
    detail = '{"code":500,"message":"Something broke"}'
    message, _hint = explain_api_error(500, detail, "store-sales-time-series-forecasting")
    assert "Something broke" in message


def _fake_result(score: float, name: str = "candidate") -> dict:
    return {
        "competition": "store-sales",
        "source": "kaggle",
        "models": [{"id": "blend", "title": "提出する予測", "status": "ok", "rmsle": score}],
        "method_version": name,
    }


def test_archive_run_is_immutable_and_listed(tmp_path: Path):
    from retail_lab.tracking import archive_run, list_runs

    out = tmp_path / "outputs" / "store-sales"
    out.mkdir(parents=True)
    (out / "result.json").write_text(json.dumps(_fake_result(0.4)), encoding="utf-8")
    (out / "submission.csv").write_text("id,sales\n1,1.0\n", encoding="utf-8")

    record = archive_run(out, run_id="run-a", label="baseline")

    assert record["run_id"] == "run-a"
    assert record["local_rmsle"] == 0.4
    assert (out / "runs" / "run-a" / "submission.csv").exists()
    assert list_runs(out)[0]["run_id"] == "run-a"
    with pytest.raises(FileExistsError):
        archive_run(out, run_id="run-a", label="overwrite")


def test_archive_run_keeps_prediction_cache(tmp_path: Path):
    from retail_lab.tracking import archive_run, load_cached_preds, write_preds

    out = tmp_path / "outputs" / "store-sales"
    out.mkdir(parents=True)
    (out / "result.json").write_text(json.dumps(_fake_result(0.4)), encoding="utf-8")
    (out / "submission.csv").write_text("id,sales\n1,1.0\n", encoding="utf-8")
    val = pd.DataFrame({"row_id": [1], "pred": [1.5]})
    write_preds(out, {"chronos2": val}, {"chronos2": val})
    archive_run(out, run_id="run-a", label="cached")
    loaded = load_cached_preds(out / "runs" / "run-a", "chronos2")
    assert loaded is not None
    assert loaded[0]["pred"].tolist() == [1.5]


def test_champion_uses_the_holdout_score_when_both_runs_have_one(tmp_path: Path):
    """当てはめた点数が良くても、隠して採点した点数が悪いRunは昇格させない。"""
    from retail_lab.tracking import archive_run, champion, consider_champion, set_holdout

    out = tmp_path / "outputs" / "store-sales"
    out.mkdir(parents=True)
    for run_id, fitted, holdout in (("old", 0.40, 0.42), ("new", 0.38, 0.45)):
        result = _fake_result(fitted, run_id)
        for model in result["models"]:
            if model["id"] == "blend":
                model["holdout_rmsle"] = holdout
        (out / "result.json").write_text(json.dumps(result), encoding="utf-8")
        (out / "submission.csv").write_text(f"id,sales\n1,{fitted}\n", encoding="utf-8")
        archive_run(out, run_id=run_id, label=run_id)
        consider_champion(out, run_id)

    assert champion(out)["run_id"] == "old"
    set_holdout(out, "new", 0.41)
    assert consider_champion(out, "new") is True
    assert champion(out)["run_id"] == "new"


def test_better_run_becomes_champion_and_worse_run_does_not(tmp_path: Path):
    from retail_lab.tracking import archive_run, champion, consider_champion

    out = tmp_path / "outputs" / "store-sales"
    out.mkdir(parents=True)

    for run_id, score in (("run-a", 0.4), ("run-b", 0.38), ("run-c", 0.42)):
        (out / "result.json").write_text(json.dumps(_fake_result(score, run_id)), encoding="utf-8")
        (out / "submission.csv").write_text(f"id,sales\n1,{score}\n", encoding="utf-8")
        archive_run(out, run_id=run_id, label=run_id)
        consider_champion(out, run_id)

    assert champion(out)["run_id"] == "run-b"
    restored = json.loads((out / "result.json").read_text(encoding="utf-8"))
    assert restored["method_version"] == "run-b"


def test_tag_and_rollback_restore_an_old_run(tmp_path: Path):
    from retail_lab.tracking import archive_run, promote_run, tag_run

    out = tmp_path / "outputs" / "store-sales"
    out.mkdir(parents=True)
    for run_id, score in (("old", 0.4), ("new", 0.38)):
        (out / "result.json").write_text(json.dumps(_fake_result(score, run_id)), encoding="utf-8")
        (out / "submission.csv").write_text(f"id,sales\n1,{score}\n", encoding="utf-8")
        archive_run(out, run_id=run_id, label=run_id)

    tag_run(out, "safe", "old")
    promote_run(out, "safe")

    restored = json.loads((out / "result.json").read_text(encoding="utf-8"))
    assert restored["method_version"] == "old"


def test_recursive_forecast_never_reads_future_targets():
    """検証の正解を値を変えても、予測は変わらない（未来漏洩がない）。"""
    from retail_lab.competitions.store_sales.recursive import fit_predict

    dates = pd.date_range("2017-01-01", periods=100)
    train_rows = []
    future_rows = []
    row_id = 0
    for store in (1, 2):
        for i, date in enumerate(dates):
            row = {
                "row_id": row_id,
                "series_id": f"{store}::A",
                "date": date,
                "target": float(10 + store + i % 7),
                "family": "A",
                "store_nbr": store,
                "type": "A",
                "cluster": store,
                "onpromotion": 0.0,
                "promo_log": 0.0,
                "oil": 50.0,
                "oil_lag7": 50.0,
                "dow": date.weekday(),
                "day": date.day,
                "month": date.month,
                "week": int(date.isocalendar().week),
                "is_weekend": int(date.weekday() >= 5),
                "is_payday": 0,
                "is_national_holiday": 0,
                "is_local_holiday": 0,
                "is_earthquake": 0,
                "transactions_lag16": 100.0,
                **EXOG_DEFAULTS,
            }
            row_id += 1
            (train_rows if i < 93 else future_rows).append(row)
    train = pd.DataFrame(train_rows)
    future = pd.DataFrame(future_rows)
    changed = future.copy()
    changed["target"] = 999999.0

    first, _ = fit_predict(train, future, n_estimators=8, context_days=100)
    second, _ = fit_predict(train, changed, n_estimators=8, context_days=100)

    assert first.sort_values("row_id")["pred"].tolist() == pytest.approx(
        second.sort_values("row_id")["pred"].tolist()
    )


def test_recursive_tweedie_never_reads_future_targets_and_stays_nonnegative():
    from retail_lab.competitions.store_sales.recursive import fit_predict

    dates = pd.date_range("2017-01-01", periods=100)
    train_rows = []
    future_rows = []
    row_id = 0
    for store in (1, 2):
        for i, date in enumerate(dates):
            row = {
                "row_id": row_id,
                "series_id": f"{store}::A",
                "date": date,
                "target": float((10 + store + i % 7) if i % 3 else 0),
                "family": "A",
                "store_nbr": store,
                "type": "A",
                "cluster": store,
                "onpromotion": 0.0,
                "promo_log": 0.0,
                "oil": 50.0,
                "oil_lag7": 50.0,
                "dow": date.weekday(),
                "day": date.day,
                "month": date.month,
                "week": int(date.isocalendar().week),
                "is_weekend": int(date.weekday() >= 5),
                "is_payday": 0,
                "is_national_holiday": 0,
                "is_local_holiday": 0,
                "is_earthquake": 0,
                "transactions_lag16": 100.0,
                **EXOG_DEFAULTS,
            }
            row_id += 1
            (train_rows if i < 93 else future_rows).append(row)
    train = pd.DataFrame(train_rows)
    future = pd.DataFrame(future_rows)
    changed = future.copy()
    changed["target"] = 999999.0

    first, _ = fit_predict(train, future, n_estimators=8, context_days=100, objective="tweedie")
    second, _ = fit_predict(train, changed, n_estimators=8, context_days=100, objective="tweedie")

    assert first.sort_values("row_id")["pred"].tolist() == pytest.approx(
        second.sort_values("row_id")["pred"].tolist()
    )
    assert (first["pred"] >= 0).all()


def test_recursive_forecast_returns_every_row_nonnegative():
    from retail_lab.competitions.store_sales.recursive import fit_predict

    panel = _panel(days=90, horizon=4)
    for column, value in {
        "family": "A",
        "store_nbr": 1,
        "type": "A",
        "cluster": 1,
        "onpromotion": 0.0,
        "promo_log": 0.0,
        "oil": 50.0,
        "oil_lag7": 50.0,
        "dow": 1,
        "day": 1,
        "month": 1,
        "week": 1,
        "is_weekend": 0,
        "is_payday": 0,
        "is_national_holiday": 0,
        "is_local_holiday": 0,
        "is_earthquake": 0,
        "transactions_lag16": 100.0,
        **EXOG_DEFAULTS,
    }.items():
        panel[column] = value
    split = split_panel(panel, 4)

    prediction, _ = fit_predict(split.train, split.val, n_estimators=8, context_days=100)

    assert len(prediction) == len(split.val)
    assert prediction["row_id"].is_unique
    assert prediction["pred"].notna().all()
    assert (prediction["pred"] >= 0).all()


def test_direct_horizon_forecast_never_reads_future_targets():
    """各予測日を一括で出すモデルも、検証の正解には触れない。"""
    from retail_lab.competitions.store_sales.direct import fit_predict

    panel = _panel(days=90, horizon=4)
    for column, value in {
        "family": "A",
        "store_nbr": 1,
        "type": "A",
        "cluster": 1,
        "onpromotion": 0.0,
        "promo_log": 0.0,
        "oil": 50.0,
        "oil_lag7": 50.0,
        "dow": 1,
        "day": 1,
        "month": 1,
        "week": 1,
        "is_weekend": 0,
        "is_payday": 0,
        "is_national_holiday": 0,
        "is_local_holiday": 0,
        "is_earthquake": 0,
        "transactions_lag16": 100.0,
        **EXOG_DEFAULTS,
    }.items():
        panel[column] = value
    split = split_panel(panel, 4)
    changed = split.val.copy()
    changed["target"] = 999999.0

    first, _ = fit_predict(split.train, split.val, n_estimators=8, context_days=100)
    second, _ = fit_predict(split.train, changed, n_estimators=8, context_days=100)

    assert first.sort_values("row_id")["pred"].tolist() == pytest.approx(
        second.sort_values("row_id")["pred"].tolist()
    )
    assert len(first) == len(split.val)
    assert first["row_id"].is_unique
    assert first["pred"].notna().all()
    assert (first["pred"] >= 0).all()


def test_recursive_drop_earthquake_does_not_read_future_targets():
    from retail_lab.competitions.store_sales.recursive import fit_predict

    panel = _panel(days=90, horizon=4)
    for column, value in {
        "family": "A",
        "store_nbr": 1,
        "type": "A",
        "cluster": 1,
        "onpromotion": 0.0,
        "promo_log": 0.0,
        "oil": 50.0,
        "oil_lag7": 50.0,
        "dow": 1,
        "day": 1,
        "month": 1,
        "week": 1,
        "is_weekend": 0,
        "is_payday": 0,
        "is_national_holiday": 0,
        "is_local_holiday": 0,
        "is_earthquake": 0,
        "transactions_lag16": 100.0,
        **EXOG_DEFAULTS,
    }.items():
        panel[column] = value
    panel.loc[panel["date"] < panel["date"].min() + pd.Timedelta(days=10), "is_earthquake"] = 1
    split = split_panel(panel, 4)
    changed = split.val.copy()
    changed["target"] = 999999.0
    first, _ = fit_predict(
        split.train, split.val, n_estimators=8, context_days=100, drop_earthquake=True
    )
    second, _ = fit_predict(
        split.train, changed, n_estimators=8, context_days=100, drop_earthquake=True
    )
    assert first.sort_values("row_id")["pred"].tolist() == pytest.approx(
        second.sort_values("row_id")["pred"].tolist()
    )


def test_snap_small_to_zero_only_touches_rows_under_the_threshold():
    from retail_lab import blending

    pred = pd.DataFrame(
        {
            "row_id": [1, 2, 3],
            "series_id": "1::A",
            "date": pd.Timestamp("2017-01-01"),
            "pred": [0.0, 0.2, 1.5],
        }
    )
    snapped = blending.snap_small_to_zero(pred, 0.3)

    assert snapped["pred"].tolist() == [0.0, 0.0, 1.5]
    assert blending.snap_small_to_zero(pred, 0.0)["pred"].tolist() == [0.0, 0.2, 1.5]


def test_choose_blend_reports_the_small_prediction_floor_it_selected():
    """しきい値は、重みを当てはめていない系列での採点で選ぶ。"""
    from retail_lab import blending

    panel = _panel(days=60, horizon=4)
    split = split_panel(panel, 4)
    preds = {}
    for name, scale in (("a", 1.0), ("b", 1.1)):
        frame = split.val[["row_id", "date", "series_id"]].copy()
        frame["pred"] = scale
        preds[name] = frame
    choice = blending.choose_blend(preds, dict(preds), split.train, split.val, split.labeled)

    assert "small_floor" in choice
    assert choice["small_floor"] >= 0.0
    assert (choice["val"]["pred"] >= 0).all()


def test_intermittent_features_match_between_training_and_recursion():
    """学習側と再帰予測側で、同じ履歴からは同じ特徴が出る。"""
    from retail_lab.competitions.store_sales import recursive

    values = [0.0, 3.0, 0.0, 0.0, 5.0] * 30
    dates = pd.date_range("2016-01-01", periods=len(values) + 1)
    frame = pd.DataFrame(
        {
            "row_id": range(len(dates)),
            "series_id": "1::A",
            "date": dates,
            "target": [*values, 7.0],
            "family": "A",
        }
    )
    featured = recursive._training_features(frame, intermittent=True)
    last = featured.iloc[-1]
    from_history = recursive._intermittent_of_history(values)

    for name in recursive.INTERMITTENT_FEATURES:
        assert float(last[name]) == pytest.approx(from_history[name]), name


def test_intermittent_features_count_the_gap_since_the_last_sale():
    from retail_lab.competitions.store_sales import recursive

    assert recursive._days_since_sale_of_history([4.0, 0.0, 0.0]) == 3.0
    assert recursive._days_since_sale_of_history([0.0, 0.0, 6.0]) == 1.0
    assert recursive._days_since_sale_of_history([0.0] * 80) == float(recursive.SALE_GAP_CAP)
    assert recursive._days_since_sale_of_history([]) == float(recursive.SALE_GAP_CAP)
    # 予測値がわずかでも売れた扱いにならないよう、しきい値で切る
    assert recursive._days_since_sale_of_history([9.0, 0.2]) == 2.0


def test_recursive_hurdle_splits_chance_and_amount_without_reading_the_future():
    from retail_lab.competitions.store_sales.recursive import fit_predict

    dates = pd.date_range("2017-01-01", periods=140)
    rows = []
    row_id = 0
    for store in (1, 2):
        for i, date in enumerate(dates):
            rows.append(
                {
                    "row_id": row_id,
                    "series_id": f"{store}::A",
                    "date": date,
                    "target": float((6 + store) if i % 5 == 0 else 0),
                    "family": "A",
                    "store_nbr": store,
                    "type": "A",
                    "cluster": store,
                    "onpromotion": 0.0,
                    "promo_log": 0.0,
                    "oil": 50.0,
                    "oil_lag7": 50.0,
                    "dow": date.weekday(),
                    "day": date.day,
                    "month": date.month,
                    "week": int(date.isocalendar().week),
                    "is_weekend": int(date.weekday() >= 5),
                    "is_payday": 0,
                    "is_national_holiday": 0,
                    "is_local_holiday": 0,
                    "is_earthquake": 0,
                    "transactions_lag16": 100.0,
                    **EXOG_DEFAULTS,
                }
            )
            row_id += 1
    panel = pd.DataFrame(rows)
    train = panel[panel["date"] < dates[-8]]
    future = panel[panel["date"] >= dates[-8]]
    changed = future.copy()
    changed["target"] = 999999.0

    first, _ = fit_predict(
        train, future, n_estimators=8, context_days=140, intermittent=True, hurdle=True
    )
    second, _ = fit_predict(
        train, changed, n_estimators=8, context_days=140, intermittent=True, hurdle=True
    )

    assert first.sort_values("row_id")["pred"].tolist() == pytest.approx(
        second.sort_values("row_id")["pred"].tolist()
    )
    assert (first["pred"] >= 0).all()


def test_recursive_hurdle_falls_back_when_every_day_sells():
    """売れない日がない系統では、ふつうの回帰に戻す。"""
    from retail_lab.competitions.store_sales.recursive import fit_predict

    panel = _panel(days=90, horizon=4)
    for column, value in {
        "family": "A",
        "store_nbr": 1,
        "type": "A",
        "cluster": 1,
        "onpromotion": 0.0,
        "promo_log": 0.0,
        "oil": 50.0,
        "oil_lag7": 50.0,
        "dow": 1,
        "day": 1,
        "month": 1,
        "week": 1,
        "is_weekend": 0,
        "is_payday": 0,
        "is_national_holiday": 0,
        "is_local_holiday": 0,
        "is_earthquake": 0,
        "transactions_lag16": 100.0,
        **EXOG_DEFAULTS,
    }.items():
        panel[column] = value
    panel["target"] = panel["target"].abs() + 5.0
    split = split_panel(panel, 4)

    preds, _ = fit_predict(split.train, split.val, n_estimators=8, context_days=100, hurdle=True)

    assert len(preds) == len(split.val)
    assert (preds["pred"] >= 0).all()


def test_recursive_hurdle_rejects_objectives_it_cannot_combine():
    from retail_lab.competitions.store_sales.recursive import fit_predict

    with pytest.raises(ValueError):
        fit_predict(pd.DataFrame(), pd.DataFrame(), objective="tweedie", hurdle=True)


def test_recursive_intermittent_does_not_read_future_targets():
    from retail_lab.competitions.store_sales.recursive import fit_predict

    dates = pd.date_range("2017-01-01", periods=140)
    rows = []
    row_id = 0
    for store in (1, 2):
        for i, date in enumerate(dates):
            rows.append(
                {
                    "row_id": row_id,
                    "series_id": f"{store}::A",
                    "date": date,
                    "target": float((4 + store) if i % 4 == 0 else 0),
                    "family": "A",
                    "store_nbr": store,
                    "type": "A",
                    "cluster": store,
                    "onpromotion": 0.0,
                    "promo_log": 0.0,
                    "oil": 50.0,
                    "oil_lag7": 50.0,
                    "dow": date.weekday(),
                    "day": date.day,
                    "month": date.month,
                    "week": int(date.isocalendar().week),
                    "is_weekend": int(date.weekday() >= 5),
                    "is_payday": 0,
                    "is_national_holiday": 0,
                    "is_local_holiday": 0,
                    "is_earthquake": 0,
                    "transactions_lag16": 100.0,
                    **EXOG_DEFAULTS,
                }
            )
            row_id += 1
    panel = pd.DataFrame(rows)
    train = panel[panel["date"] < dates[-8]]
    future = panel[panel["date"] >= dates[-8]]
    changed = future.copy()
    changed["target"] = 999999.0

    first, ranked = fit_predict(train, future, n_estimators=8, context_days=140, intermittent=True)
    second, _ = fit_predict(train, changed, n_estimators=8, context_days=140, intermittent=True)

    assert first.sort_values("row_id")["pred"].tolist() == pytest.approx(
        second.sort_values("row_id")["pred"].tolist()
    )
    assert (first["pred"] >= 0).all()
    assert {str(item["feature"]) for item in ranked} >= {"recursive_days_since_sale"}


def test_panel_adds_regional_holiday_eve_and_known_promo_leads(tmp_path: Path):
    """地域祝日・前夜・プロモの先行は、提出CSVに載っている情報だけで作る。"""
    from retail_lab.competitions.store_sales.data import Bundle, complete_daily_grid
    from retail_lab.competitions.store_sales.demo import generate_demo
    from retail_lab.competitions.store_sales.features import build_panel

    generate_demo(tmp_path)
    holidays = pd.read_csv(tmp_path / "holidays_events.csv")
    holidays.loc[holidays["date"] == "2017-08-10", "transferred"] = True
    holidays.loc[len(holidays)] = {
        "date": "2017-08-11",
        "type": "Holiday",
        "locale": "Regional",
        "locale_name": "Pichincha",
        "description": "Regional test",
        "transferred": False,
    }
    holidays.to_csv(tmp_path / "holidays_events.csv", index=False)

    train = pd.read_csv(tmp_path / "train.csv", parse_dates=["date"])
    train.loc[
        (train["date"] == "2017-08-12")
        & (train["store_nbr"] == 1)
        & (train["family"] == "GROCERY I"),
        "onpromotion",
    ] = 9
    train.to_csv(tmp_path / "train.csv", index=False)

    bundle = Bundle(
        train=complete_daily_grid(train),
        test=pd.read_csv(tmp_path / "test.csv", parse_dates=["date"]),
        stores=pd.read_csv(tmp_path / "stores.csv"),
        oil=pd.read_csv(tmp_path / "oil.csv", parse_dates=["date"]),
        holidays=pd.read_csv(tmp_path / "holidays_events.csv", parse_dates=["date"]),
        transactions=pd.read_csv(tmp_path / "transactions.csv", parse_dates=["date"]),
        source="demo",
        data_dir=tmp_path,
    )
    bundle.holidays["transferred"] = (
        bundle.holidays["transferred"].astype(str).str.lower().isin(["true", "1"])
    )
    panel = build_panel(bundle)
    eve = panel[(panel["date"] == "2017-08-10") & (panel["family"] == "GROCERY I")]
    holiday = panel[(panel["date"] == "2017-08-11") & (panel["family"] == "GROCERY I")]
    transferred = panel[(panel["date"] == "2017-08-10") & (panel["family"] == "GROCERY I")]
    lead = panel[
        (panel["date"] == "2017-08-11")
        & (panel["store_nbr"] == 1)
        & (panel["family"] == "GROCERY I")
    ]

    assert set(holiday.loc[holiday["state"] == "Pichincha", "is_regional_holiday"]) == {1}
    assert set(holiday.loc[holiday["state"] != "Pichincha", "is_regional_holiday"]) == {0}
    assert set(eve.loc[eve["state"] == "Pichincha", "is_holiday_eve"]) == {1}
    assert set(transferred["is_national_holiday"]) == {0}
    assert float(lead["promo_lead_1"].iloc[0]) == 9.0
