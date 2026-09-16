"""Kaggle Store Sales（Favorita / エクアドル）。

読む順番: spec.py（何を当てるか）→ data.py（読み込み）→ features.py（特徴）→ prepare()。
"""

from __future__ import annotations

from functools import partial
from pathlib import Path

from retail_lab.competition import CandidateModel, Prepared
from retail_lab.competitions.store_sales import data, direct, features, recursive
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
            ),
            CandidateModel(
                id="recursive_lgbm_no_eq",
                title="再帰 LightGBM（地震期間を学習から除外）",
                note=(
                    "2016年4〜5月の地震需要を学習から外す。"
                    "予測時の特徴は残し、異常な売上だけを教師に使わない。"
                ),
                predict=partial(recursive.fit_predict, drop_earthquake=True),
                org="custom",
            ),
            CandidateModel(
                id="recursive_short",
                title="再帰 LightGBM（直近180日）",
                note=(
                    "履歴を180日に絞る。古い需要構造を捨て、間欠な系統の形を直近に合わせる。"
                ),
                predict=partial(recursive.fit_predict, context_days=180),
                org="custom",
            ),
            CandidateModel(
                id="recursive_tweedie",
                title="再帰 LightGBM（Tweedie・365日）",
                note=(
                    "ゼロが多い売上向けの Tweedie 目的関数。"
                    "LINGERIE など間欠需要の過小予測を抑える。"
                ),
                predict=partial(
                    recursive.fit_predict, context_days=365, objective="tweedie"
                ),
                org="custom",
            ),
            CandidateModel(
                id="direct_horizon_lgbm",
                title="予測距離別 LightGBM",
                note=(
                    "1〜16日の予測距離ごとに、その時点で既知の直近値と"
                    "週次ラグを選ぶ。再帰しないため予測誤差が翌日に連鎖しない。"
                ),
                predict=direct.fit_predict,
                org="custom",
            ),
        ],
        extra={"data_dir": str(bundle.data_dir)},
    )
