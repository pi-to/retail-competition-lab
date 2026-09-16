"""データ読込→特徴量→複数モデル→混合→提出CSVの結合テスト。"""

from pathlib import Path

import pandas as pd

from retail_lab.competitions import store_sales
from retail_lab.experiment import run_experiment


def test_demo_pipeline_builds_a_valid_submission_and_report(tmp_path: Path):
    prepared = store_sales.prepare(tmp_path, "demo")
    output = tmp_path / "outputs" / "store-sales"

    result = run_experiment(prepared, output, skip_foundation=True)

    submission = pd.read_csv(output / "submission.csv")
    assert result["source"] == "demo"
    assert result["n_series"] == 24
    assert result["report"]["data_usage"]
    assert {model["id"] for model in result["models"]} >= {
        "seasonal_naive",
        "lightgbm",
        "recursive_lgbm",
        "blend",
    }
    assert list(submission.columns) == ["id", "sales"]
    assert len(submission) == 24 * 16
    assert submission["id"].is_unique
    assert submission["sales"].notna().all()
    assert (submission["sales"] >= 0).all()
