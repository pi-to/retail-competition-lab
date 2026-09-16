"""Kaggle Store Sales（Favorita / エクアドル）。

読む順番: spec.py（何を当てるか）→ data.py（読み込み）→ features.py（特徴）→ prepare()。
"""

from __future__ import annotations

from pathlib import Path

from retail_lab.competition import Prepared
from retail_lab.competitions.store_sales import data, features
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
        extra={"data_dir": str(bundle.data_dir)},
    )
