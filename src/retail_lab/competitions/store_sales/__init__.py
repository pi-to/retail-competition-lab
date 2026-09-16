"""Kaggle Store Sales（Favorita / エクアドル）。

読む順番: spec.py（何を当てるか）→ data.py（読み込み）→ features.py（特徴）→ prepare()。
"""

from __future__ import annotations

from pathlib import Path

from retail_lab.competition import CandidateModel, Prepared
from retail_lab.competitions.store_sales import data, features, recursive
from retail_lab.competitions.store_sales.spec import SPEC

__all__ = ["SPEC", "prepare"]


def prepare(root: Path, source: str) -> Prepared:
    bundle = data.load_bundle(root, source)
    panel = features.build_panel(bundle)
    return Prepared(
        spec=SPEC,
        source=bundle.source,
        panel=panel,
        features=features.GBDT_FEATURES,
        categoricals=features.CATEGORICALS,
        covariates=features.CHRONOS_COVARIATES,
        candidates=[
            CandidateModel(
                id="recursive_lgbm",
                title="再帰 LightGBM（ファミリー別）",
                note=(
                    "商品ファミリーごとに学習し、1日ずつ予測を履歴へ戻す。"
                    "直近1・7・14日の週次リズムを未来漏洩なしで使う。"
                ),
                predict=recursive.fit_predict,
                org="custom",
            )
        ],
        extra={"data_dir": str(bundle.data_dir)},
    )
