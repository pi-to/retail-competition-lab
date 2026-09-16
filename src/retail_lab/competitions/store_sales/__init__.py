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
                note=("履歴を180日に絞る。古い需要構造を捨て、間欠な系統の形を直近に合わせる。"),
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
                predict=partial(recursive.fit_predict, context_days=365, objective="tweedie"),
                org="custom",
            ),
            CandidateModel(
                id="recursive_intermittent",
                title="再帰 LightGBM（売れない日と水準の動きを見る）",
                note=(
                    "最後に売れてからの日数、ゼロの割合、直近28日と112日の水準比を足す。"
                    "LINGERIE の間欠需要と GROCERY II の水準変化向け。"
                ),
                predict=partial(recursive.fit_predict, intermittent=True),
                org="custom",
            ),
            CandidateModel(
                id="recursive_intermittent_short",
                title="再帰 LightGBM（間欠特徴・直近180日）",
                note=(
                    "同じ特徴を直近180日だけで学習する。"
                    "水準が変わった系統を、古い水準に引っ張られずに追う。"
                ),
                predict=partial(recursive.fit_predict, context_days=180, intermittent=True),
                org="custom",
            ),
            CandidateModel(
                id="recursive_intermittent_deep",
                title="再帰 LightGBM（間欠特徴・細かい木）",
                note=(
                    "同じ特徴を、葉63・学習率0.03・木560本で学習する。"
                    "外れ方が浅い木と違うので、混ぜると補い合う。"
                ),
                predict=partial(
                    recursive.fit_predict,
                    intermittent=True,
                    n_estimators=560,
                    learning_rate=0.03,
                    num_leaves=63,
                ),
                org="custom",
            ),
            CandidateModel(
                id="recursive_intermittent_tweedie",
                title="再帰 LightGBM（間欠特徴・Tweedie）",
                note=(
                    "ゼロ込みの売上分布に合う Tweedie で、間欠特徴つきの365日学習。"
                    "下着売り場のような売れない日が多い系統向け。"
                ),
                predict=partial(
                    recursive.fit_predict,
                    intermittent=True,
                    context_days=365,
                    objective="tweedie",
                ),
                org="custom",
            ),
            CandidateModel(
                id="recursive_hurdle",
                title="再帰 LightGBM（売れるか × 売れたらいくら）",
                note=(
                    "「その日売れるか」と「売れたらいくらか」を別に学び、掛けて戻す。"
                    "売れない日が多い売り場で、日ごとの当たり外れを分けて扱う。"
                ),
                predict=partial(recursive.fit_predict, intermittent=True, hurdle=True),
                org="custom",
            ),
            CandidateModel(
                id="recursive_hurdle_deep",
                title="再帰 LightGBM（売れるか × いくら・細かい木）",
                note=(
                    "売れるか／いくらの2段構えを、葉63・木560本で学ぶ。"
                    "同じ考え方でも当たる行がずれるので、混ぜる相手になる。"
                ),
                predict=partial(
                    recursive.fit_predict,
                    intermittent=True,
                    hurdle=True,
                    n_estimators=560,
                    learning_rate=0.03,
                    num_leaves=63,
                ),
                org="custom",
            ),
            CandidateModel(
                id="recursive_hurdle_short",
                title="再帰 LightGBM（売れるか × いくら・直近180日）",
                note=(
                    "2段構えを直近180日だけで学ぶ。"
                    "売れ方が最近変わった棚を、古い頻度に引っ張られずに追う。"
                ),
                predict=partial(
                    recursive.fit_predict,
                    intermittent=True,
                    hurdle=True,
                    context_days=180,
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
            CandidateModel(
                id="direct_intermittent",
                title="予測距離別 LightGBM（売れない間隔つき）",
                note=(
                    "予測の起点までに売れていない日の続き方と水準の動きを足す。"
                    "再帰しないので、誤差は翌日に連鎖しない。"
                ),
                predict=partial(direct.fit_predict, intermittent=True),
                org="custom",
            ),
            CandidateModel(
                id="direct_hurdle",
                title="予測距離別 LightGBM（売れるか × いくら）",
                note=(
                    "距離別の一括予測でも、売れる確率と量を分けて学ぶ。"
                    "再帰モデルとは外れ方が違うので混ぜる相手になる。"
                ),
                predict=partial(direct.fit_predict, intermittent=True, hurdle=True),
                org="custom",
            ),
            CandidateModel(
                id="direct_family_trend",
                title="予測距離別 LightGBM（売り場全体の勢い）",
                note=(
                    "全54店で同じ売り場が最近増えたか減ったかを足す。"
                    "GROCERY II のような全体の水準変化を各店へ伝える。"
                ),
                predict=partial(direct.fit_predict, intermittent=True, family_trend=True),
                org="custom",
            ),
            CandidateModel(
                id="direct_family_trend_hurdle",
                title="予測距離別 LightGBM（売り場の勢い × 2段構え）",
                note=(
                    "売り場全体の勢いを見ながら、売れる確率と量を別に学ぶ。"
                    "店舗単独の偶然と全店共通の変化を分ける。"
                ),
                predict=partial(
                    direct.fit_predict,
                    intermittent=True,
                    hurdle=True,
                    family_trend=True,
                ),
                org="custom",
            ),
        ],
        extra={"data_dir": str(bundle.data_dir)},
    )
