"""コンペをまたいで共通の実験ループ。

ナイーブ → 表モデル → 基盤モデル2種 → 混合、の順に同じ検証窓で採点する。
コンペ側が用意するのはデータと特徴だけ。
"""

from __future__ import annotations

import json
import time
import traceback
from pathlib import Path
from typing import Any

import pandas as pd

from retail_lab import DATE, ROW_ID, SERIES_ID, TARGET, blending
from retail_lab.competition import Prepared
from retail_lab.models import chronos, gbdt, naive, timesfm
from retail_lab.status import write_status
from retail_lab.tracking import load_cached_preds, write_preds
from retail_lab.validation import Split, split_panel

JsonDict = dict[str, Any]
PRED = "pred"


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def _preview(split: Split, pred_map: dict[str, pd.DataFrame], blended: pd.DataFrame) -> JsonDict:
    """一番売れている系列だけを抜き出して、当たり方を目で見られるようにする。"""
    totals = split.train.groupby(SERIES_ID)[TARGET].sum().sort_values(ascending=False)
    sid = str(totals.index[0])
    hist = split.train[split.train[SERIES_ID] == sid].sort_values(DATE).tail(42)
    actual = split.val[split.val[SERIES_ID] == sid].sort_values(DATE)
    models: dict[str, list[JsonDict]] = {}
    for name, frame in {**pred_map, "blend": blended}.items():
        sub = frame[frame[SERIES_ID] == sid].sort_values(DATE)
        models[name] = [
            {"date": d.strftime("%Y-%m-%d"), "pred": float(p)}
            for d, p in zip(sub[DATE], sub[PRED], strict=True)
        ]
    return {
        "series_id": sid,
        "history": [
            {"date": d.strftime("%Y-%m-%d"), "sales": float(v)}
            for d, v in zip(hist[DATE], hist[TARGET], strict=True)
        ],
        "actual": [
            {"date": d.strftime("%Y-%m-%d"), "sales": float(v)}
            for d, v in zip(actual[DATE], actual[TARGET], strict=True)
        ],
        "models": models,
    }


def _client_report(
    prepared: Prepared, split: Split, models_meta: list[JsonDict], n_series: int
) -> JsonDict:
    """非エンジニアが読む前提のまとめ。数字の意味を文章で添える。"""
    horizon = prepared.spec.horizon
    by_id = {m["id"]: m for m in models_meta if m.get("status") == "ok"}
    blend = by_id.get("blend")
    base = by_id.get("seasonal_naive")

    usage: list[JsonDict] = [
        {
            "label": "学習に使った期間",
            "value": f"{split.train[DATE].min().date()} 〜 {split.train[DATE].max().date()}",
            "detail": f"{int(split.train[DATE].nunique())}日分 / {len(split.train):,}行",
        },
        {
            "label": "答え合わせに使った期間",
            "value": f"{split.val[DATE].min().date()} 〜 {split.val[DATE].max().date()}",
            "detail": f"{int(split.val[DATE].nunique())}日分 / {len(split.val):,}行",
        },
        {
            "label": "予測した組み合わせ",
            "value": f"{n_series:,} 系列",
            "detail": prepared.spec.unit,
        },
        {
            "label": "検証の作り方",
            "value": f"最後の{horizon}日を隠す",
            "detail": f"全モデルがこの{horizon}日を一切見ずに予測し、あとで実績と突き合わせた",
        },
    ]

    interpretation: list[JsonDict] = []
    if blend is not None:
        low = 100 * (1 - blend["wape"])
        high = 100 * (1 + blend["wape"])
        interpretation.append(
            {
                "title": "どれくらい当たったか",
                "body": (
                    f"採用した予測は、隠した{horizon}日間の合計に対して平均 "
                    f"{_pct(blend['wape'])} ずれました。"
                    f"言い換えると、100個売れる日を約{low:.0f}〜{high:.0f}個の幅で見込めています。"
                ),
            }
        )
    if blend is not None and base is not None and base["wape"] > 0:
        gain = 1 - blend["wape"] / base["wape"]
        body = (
            f"「先週の同じ曜日と同じだけ売れる」と考える単純な方法は同じ期間で "
            f"{_pct(base['wape'])} ずれました。"
            f"採用した予測はその誤差を {_pct(gain)} 減らしています。"
            if gain > 0
            else (
                f"単純な方法は {_pct(base['wape'])} でした。"
                "今回のデータでは差が出ていないので、特徴やモデルを足す余地があります。"
            )
        )
        interpretation.append({"title": "勘と比べてどうか", "body": body})
    if blend is not None:
        direction = "多め" if blend["bias"] > 0 else "少なめ"
        interpretation.append(
            {
                "title": "外れ方の癖",
                "body": (
                    f"合計では実績より {_pct(abs(blend['bias']))} {direction}に見込んでいます。"
                    f"個別の予測では {_pct(blend['under_rate'])} が実績より少ない値で、"
                    "ここが欠品につながる側です。"
                    "発注に使うときは、この比率を見て安全在庫を決められます。"
                ),
            }
        )
    interpretation.append(
        {
            "title": "この数字の読み方の注意",
            "body": (
                "公式データで測った結果なので、Kaggle に提出したときのスコアの目安になります。"
                if prepared.source == "kaggle"
                else (
                    "いまはデモ用の縮小データです。手順が動くことの確認用で、"
                    "誤差の絶対値は公式データとは変わります。公式CSVで再実行すると本番の水準が出ます。"
                )
            ),
        }
    )

    return {
        "data_usage": usage,
        "interpretation": interpretation,
        "glossary": [
            {
                "term": "誤差率",
                "body": "予測と実績のずれを合計して、実績の合計で割った値。小さいほど良い。",
            },
            {
                "term": "偏り",
                "body": (
                    "全体として多めに見たか少なめに見たか。プラスは在庫過多、マイナスは欠品寄り。"
                ),
            },
            {"term": "欠品側の割合", "body": "実績より少なく見積もった予測の割合。"},
            {
                "term": "RMSLE",
                "body": "コンペの採点式。割合のずれを見る指標で、順位はこれで決まる。",
            },
        ],
    }


def run_experiment(
    prepared: Prepared,
    out_dir: Path,
    skip_foundation: bool = False,
    reuse_run: Path | None = None,
) -> JsonDict:
    started = time.time()
    spec = prepared.spec
    horizon = spec.horizon
    out_dir.mkdir(parents=True, exist_ok=True)

    split = split_panel(prepared.panel, horizon)
    labeled = split.labeled
    n_series = int(prepared.panel[SERIES_ID].nunique())

    models_meta: list[JsonDict] = []
    val_preds: dict[str, pd.DataFrame] = {}
    test_preds: dict[str, pd.DataFrame] = {}
    scores: dict[str, float] = {}
    importance: list[dict[str, float | str]] = []

    def register(
        model_id: str,
        title: str,
        note: str,
        val_df: pd.DataFrame,
        test_df: pd.DataFrame,
        extra: JsonDict | None = None,
    ) -> None:
        score = blending.score_against(val_df, split.val)
        business = blending.business_against(val_df, split.val)
        scores[model_id] = score
        val_preds[model_id] = val_df
        test_preds[model_id] = test_df
        row: JsonDict = {
            "id": model_id,
            "title": title,
            "note": note,
            "rmsle": round(score, 5),
            "status": "ok",
            "wape": round(business["wape"], 4),
            "bias": round(business["bias"], 4),
            "under_rate": round(business["under_rate"], 4),
            "mae": round(business["mae"], 2),
        }
        if extra:
            row.update(extra)
        models_meta.append(row)

    def skipped(model_id: str, title: str, checkpoint: str, org: str, exc: Exception) -> None:
        models_meta.append(
            {
                "id": model_id,
                "title": title,
                "note": "読み込みまたは推論に失敗",
                "status": "skipped",
                "error": f"{exc}",
                "checkpoint": checkpoint,
                "org": org,
            }
        )
        (out_dir / f"{model_id}_error.txt").write_text(traceback.format_exc(), encoding="utf-8")

    write_status(out_dir, "naive", "季節ナイーブ（同じ曜日の直近）", 15)
    register(
        "seasonal_naive",
        "季節ナイーブ",
        "同じ曜日の最後の実績。下限。これを大きく下回れない手法は捨てる。",
        naive.seasonal_naive(split.train, split.val),
        naive.seasonal_naive(labeled, split.future),
    )

    write_status(out_dir, "lgbm", "LightGBM（系列を横断する表モデル）", 30)
    val_gbdt, _ = gbdt.fit_predict(split.train, split.val, prepared.features, prepared.categoricals)
    test_gbdt, importance = gbdt.fit_predict(
        labeled, split.future, prepared.features, prepared.categoricals
    )
    register(
        "lightgbm",
        "LightGBM",
        f"ラグ{horizon}日以上 + プロモ + 祝日 + 原油 + 給料日 + 店属性。log1p 学習。",
        val_gbdt,
        test_gbdt,
        {"top_features": importance[:8]},
    )

    for index, candidate in enumerate(prepared.candidates):
        try:
            pct = 38 + index * 6
            write_status(out_dir, candidate.id, f"{candidate.title} が検証窓を予測中", pct)
            candidate_val, candidate_importance = candidate.predict(split.train, split.val)
            write_status(out_dir, candidate.id, f"{candidate.title} が提出分を予測中", pct + 4)
            candidate_test, _ = candidate.predict(labeled, split.future)
            register(
                candidate.id,
                candidate.title,
                candidate.note,
                candidate_val,
                candidate_test,
                {"org": candidate.org, "top_features": candidate_importance[:8]},
            )
        except Exception as exc:  # noqa: BLE001 - 候補が落ちても既存モデルで続ける
            skipped(candidate.id, candidate.title, candidate.id, candidate.org, exc)

    if not skip_foundation:
        try:
            cached = load_cached_preds(reuse_run, "chronos2") if reuse_run else None
            if cached is not None:
                write_status(out_dir, "chronos", "Chronos-2 を前回Runから再利用", 55)
                chronos_val, chronos_test = cached
            else:
                write_status(out_dir, "chronos", "Chronos-2 を読み込み中", 50)
                pipe = chronos.load_pipeline()
                write_status(
                    out_dir, "chronos", f"Chronos-2 が検証窓を予測中（{n_series:,}系列）", 55
                )
                chronos_val = chronos.forecast(
                    split.train, split.val, horizon, prepared.covariates, pipe=pipe
                )
                write_status(
                    out_dir, "chronos", f"Chronos-2 が提出分を予測中（{n_series:,}系列）", 63
                )
                chronos_test = chronos.forecast(
                    labeled, split.future, horizon, prepared.covariates, pipe=pipe
                )
                del pipe
            register(
                "chronos2",
                "Chronos-2",
                "AWS の時系列基盤モデル。数量の系列に、未来に分かる列を添えて渡す。学習しない。"
                + ("前回Runの予測を再利用。" if cached is not None else ""),
                chronos_val,
                chronos_test,
                {
                    "checkpoint": chronos.CHECKPOINT,
                    "org": chronos.ORG,
                    "reused": cached is not None,
                },
            )
        except Exception as exc:  # noqa: BLE001 - 基盤モデルが落ちても実験は続ける
            skipped("chronos2", "Chronos-2", chronos.CHECKPOINT, chronos.ORG, exc)

        try:
            cached = load_cached_preds(reuse_run, "timesfm") if reuse_run else None
            if cached is not None:
                write_status(out_dir, "timesfm", "TimesFM を前回Runから再利用", 77)
                timesfm_val, timesfm_test = cached
            else:
                write_status(out_dir, "timesfm", "TimesFM 2.5 を読み込み中", 72)
                model = timesfm.load_model(max_horizon=max(32, horizon))
                write_status(
                    out_dir, "timesfm", f"TimesFM が検証窓を予測中（{n_series:,}系列）", 77
                )
                timesfm_val = timesfm.forecast(split.train, split.val, horizon, model=model)
                write_status(
                    out_dir, "timesfm", f"TimesFM が提出分を予測中（{n_series:,}系列）", 84
                )
                timesfm_test = timesfm.forecast(labeled, split.future, horizon, model=model)
                del model
            register(
                "timesfm",
                "TimesFM 2.5",
                "Google の時系列基盤モデル。数量の並びだけを読む。AWS に依存しない対照実験。"
                + ("前回Runの予測を再利用。" if cached is not None else ""),
                timesfm_val,
                timesfm_test,
                {
                    "checkpoint": timesfm.CHECKPOINT,
                    "org": timesfm.ORG,
                    "reused": cached is not None,
                },
            )
        except Exception as exc:  # noqa: BLE001 - 同上
            skipped("timesfm", "TimesFM 2.5", timesfm.CHECKPOINT, timesfm.ORG, exc)

    write_status(out_dir, "blend", "混ぜ方とゼロ系列の窓を検証窓で選ぶ", 90)
    val_preds, test_preds = blending.with_pooled_candidates(val_preds, test_preds)
    if "robust_min" in val_preds:
        register(
            "robust_min",
            "強いモデルの行ごと最小",
            "direct / 再帰 / TimesFM の行ごと最小。過大予測が多い系統向け。",
            val_preds["robust_min"],
            test_preds["robust_min"],
            {"org": "custom"},
        )
    choice = blending.choose_blend(val_preds, test_preds, split.train, split.val, labeled)
    strategy = str(choice["strategy"])
    zero_window = int(choice["zero_window"])
    val_blend = choice["val"]
    test_blend = choice["test"]
    weights: dict[str, float] = choice["weights"]
    chosen_horizon_weights = choice.get("weights_by_horizon")
    chosen_family_weights = choice.get("weights_by_family")
    best_score = float(choice["score"])
    holdout_score = choice.get("holdout_score")
    alpha = float(choice.get("alpha", 1.0))
    models_used: list[str] = list(choice.get("models_used") or [])
    best_single = str(choice["best_single"])
    per_strategy: dict[str, float] = choice["candidates"]
    blend_business = blending.business_against(val_blend, split.val)

    for row in models_meta:
        if row.get("status") == "ok":
            row["weight"] = round(weights.get(row["id"], 0.0), 4)

    notes = {
        "rule": "検証 RMSLE の逆数を重みにした。",
        "fitted": "検証窓で RMSLE を最小にする非負の重みを当てた。",
        "fitted_horizon": "予測日ごとに非負の重みを当てた。再帰の後半劣化を日別に補う。",
        "fitted_family": "商品ファミリーごとに非負の重みを当てた。系統ごとの当たり方の違いを残す。",
        "fitted_family_shrunk": "ファミリー別の重みを全体の重みへ少し寄せた。",
        "single": f"混ぜると悪化したので {best_single} 単体を採用した。",
    }
    zero_note = (
        f"直近{zero_window}日がすべて0の系列は0にした。"
        if zero_window
        else "ゼロ系列の後処理は、検証窓で悪化したので使わない。"
    )
    shrink_note = (
        f"ファミリー別の重みは全体へ{(1 - alpha) * 100:.0f}%寄せた。" if alpha < 1.0 else ""
    )
    models_meta.append(
        {
            "id": "blend",
            "title": "提出する予測",
            "note": f"{notes[strategy]}{shrink_note}{zero_note}",
            "rmsle": round(best_score, 5),
            "holdout_rmsle": (
                round(float(holdout_score), 5) if holdout_score is not None else None
            ),
            "shrinkage": round(alpha, 3),
            "models_used": models_used,
            "status": "ok",
            "weight": 1.0,
            "strategy": strategy,
            "zero_window": zero_window,
            "weights": {k: round(v, 4) for k, v in weights.items()},
            "weights_by_horizon": (
                {
                    str(step): {k: round(v, 4) for k, v in part.items()}
                    for step, part in chosen_horizon_weights.items()
                }
                if chosen_horizon_weights is not None
                else None
            ),
            "weights_by_family": (
                {
                    family: {k: round(v, 4) for k, v in part.items()}
                    for family, part in chosen_family_weights.items()
                }
                if chosen_family_weights is not None
                else None
            ),
            "candidates": {k: round(v, 5) for k, v in per_strategy.items()},
            "wape": round(blend_business["wape"], 4),
            "bias": round(blend_business["bias"], 4),
            "under_rate": round(blend_business["under_rate"], 4),
            "mae": round(blend_business["mae"], 2),
        }
    )

    submission = (
        test_blend[[ROW_ID, PRED]].rename(columns={ROW_ID: "id", PRED: "sales"}).sort_values("id")
    )
    submission.to_csv(out_dir / "submission.csv", index=False)

    val_horizon = split.val.copy()
    val_horizon["horizon"] = (val_horizon[DATE] - val_horizon[DATE].min()).dt.days + 1
    error_slices: JsonDict = {
        "horizon": blending.grouped_rmsle(val_blend, val_horizon, "horizon", worst=horizon)
    }
    if "family" in split.val.columns:
        error_slices["family"] = blending.grouped_rmsle(val_blend, split.val, "family")
    val_preds["blend"] = val_blend
    test_preds["blend"] = test_blend
    write_preds(out_dir, val_preds, test_preds)

    result: JsonDict = {
        "competition": spec.slug,
        "title": spec.title,
        "source": prepared.source,
        "horizon": horizon,
        "n_series": n_series,
        "n_train_rows": int(len(labeled)),
        "train_end": str(labeled[DATE].max().date()),
        "test_start": str(split.future[DATE].min().date()),
        "test_end": str(split.future[DATE].max().date()),
        "metric": "RMSLE",
        "models": models_meta,
        "feature_importance": importance[:16],
        "error_slices": error_slices,
        "preview": _preview(split, val_preds, val_blend),
        "method": list(spec.method),
        "report": _client_report(prepared, split, models_meta, n_series),
        "elapsed_sec": round(time.time() - started, 1),
        "kaggle_ready": prepared.source == "kaggle",
    }
    (out_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_status(out_dir, "done", "完了", 100)
    return result


def holdout_score_of_run(prepared: Prepared, run_dir: Path) -> float:
    """保存済み予測から、隠して採点した点数だけを計算する。成果物は書き換えない。

    過去Runと現在のRunを同じ物差しで比べるために使う。
    """
    from retail_lab.tracking import PRED_DIR

    pred_dir = run_dir / PRED_DIR
    val_preds: dict[str, pd.DataFrame] = {}
    test_preds: dict[str, pd.DataFrame] = {}
    for path in sorted(pred_dir.glob("*_val.parquet")):
        name = path.name.removesuffix("_val.parquet")
        test_path = pred_dir / f"{name}_test.parquet"
        if name == "blend" or not test_path.exists():
            continue
        val_preds[name] = pd.read_parquet(path)
        test_preds[name] = pd.read_parquet(test_path)
    if not val_preds:
        raise FileNotFoundError(f"再利用できる予測がありません: {pred_dir}")

    split = split_panel(prepared.panel, prepared.spec.horizon)
    val_preds, test_preds = blending.with_pooled_candidates(val_preds, test_preds)
    choice = blending.choose_blend(val_preds, test_preds, split.train, split.val, split.labeled)
    holdout = choice.get("holdout_score")
    if holdout is None:
        raise ValueError("この検証窓では隠して採点できません")
    return float(holdout)


def reblend_cached(prepared: Prepared, out_dir: Path, source_run: Path) -> JsonDict:
    """保存済みのモデル予測だけを読み、混ぜ方を検証窓でやり直す。"""
    from retail_lab.tracking import PRED_DIR

    pred_dir = source_run / PRED_DIR
    val_preds: dict[str, pd.DataFrame] = {}
    test_preds: dict[str, pd.DataFrame] = {}
    for path in sorted(pred_dir.glob("*_val.parquet")):
        name = path.name.removesuffix("_val.parquet")
        if name == "blend":
            continue
        test_path = pred_dir / f"{name}_test.parquet"
        if not test_path.exists():
            continue
        val_preds[name] = pd.read_parquet(path)
        test_preds[name] = pd.read_parquet(test_path)
    if not val_preds:
        raise FileNotFoundError(f"再利用できる予測がありません: {pred_dir}")

    split = split_panel(prepared.panel, prepared.spec.horizon)
    write_status(out_dir, "blend", "保存済み予測の混ぜ方を検証窓で選ぶ", 90)
    val_preds, test_preds = blending.with_pooled_candidates(val_preds, test_preds)
    choice = blending.choose_blend(val_preds, test_preds, split.train, split.val, split.labeled)
    strategy = str(choice["strategy"])
    zero_window = int(choice["zero_window"])
    val_blend = choice["val"]
    test_blend = choice["test"]
    weights: dict[str, float] = choice["weights"]
    chosen_horizon_weights = choice.get("weights_by_horizon")
    chosen_family_weights = choice.get("weights_by_family")
    best_score = float(choice["score"])
    holdout_score = choice.get("holdout_score")
    alpha = float(choice.get("alpha", 1.0))
    models_used: list[str] = list(choice.get("models_used") or [])
    best_single = str(choice["best_single"])
    per_strategy: dict[str, float] = choice["candidates"]
    blend_business = blending.business_against(val_blend, split.val)

    source = json.loads((source_run / "result.json").read_text(encoding="utf-8"))
    skip_ids = {"blend", "robust_min"}
    models_meta = [
        row for row in source.get("models", []) if row.get("id") not in skip_ids
    ]
    if "robust_min" in val_preds:
        robust_score = blending.score_against(val_preds["robust_min"], split.val)
        models_meta.append(
            {
                "id": "robust_min",
                "title": "強いモデルの行ごと最小",
                "note": "direct・再帰・TimesFMの行ごと最小。過大予測向け。",
                "rmsle": round(robust_score, 5),
                "status": "ok",
                "org": "custom",
            }
        )
    for row in models_meta:
        if row.get("status") == "ok":
            row["weight"] = round(weights.get(str(row.get("id")), 0.0), 4)
    notes = {
        "rule": "検証 RMSLE の逆数を重みにした。",
        "fitted": "検証窓で RMSLE を最小にする非負の重みを当てた。",
        "fitted_horizon": "予測日ごとに非負の重みを当てた。再帰の後半劣化を日別に補う。",
        "fitted_family": "商品ファミリーごとに非負の重みを当てた。系統ごとの当たり方の違いを残す。",
        "fitted_family_shrunk": "ファミリー別の重みを全体の重みへ少し寄せた。",
        "single": f"混ぜると悪化したので {best_single} 単体を採用した。",
    }
    zero_note = (
        f"直近{zero_window}日がすべて0の系列は0にした。"
        if zero_window
        else "ゼロ系列の後処理は、検証窓で悪化したので使わない。"
    )
    shrink_note = (
        f"ファミリー別の重みは全体へ{(1 - alpha) * 100:.0f}%寄せた。" if alpha < 1.0 else ""
    )
    models_meta.append(
        {
            "id": "blend",
            "title": "提出する予測",
            "note": f"{notes[strategy]}{shrink_note}{zero_note}",
            "rmsle": round(best_score, 5),
            "holdout_rmsle": (
                round(float(holdout_score), 5) if holdout_score is not None else None
            ),
            "shrinkage": round(alpha, 3),
            "models_used": models_used,
            "status": "ok",
            "weight": 1.0,
            "strategy": strategy,
            "zero_window": zero_window,
            "weights": {k: round(v, 4) for k, v in weights.items()},
            "weights_by_horizon": (
                {
                    str(step): {k: round(v, 4) for k, v in part.items()}
                    for step, part in chosen_horizon_weights.items()
                }
                if chosen_horizon_weights is not None
                else None
            ),
            "weights_by_family": (
                {
                    family: {k: round(v, 4) for k, v in part.items()}
                    for family, part in chosen_family_weights.items()
                }
                if chosen_family_weights is not None
                else None
            ),
            "candidates": {k: round(v, 5) for k, v in per_strategy.items()},
            "wape": round(blend_business["wape"], 4),
            "bias": round(blend_business["bias"], 4),
            "under_rate": round(blend_business["under_rate"], 4),
            "mae": round(blend_business["mae"], 2),
            "reblend_of": source.get("run_id"),
        }
    )
    submission = (
        test_blend[[ROW_ID, PRED]].rename(columns={ROW_ID: "id", PRED: "sales"}).sort_values("id")
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    submission.to_csv(out_dir / "submission.csv", index=False)
    val_horizon = split.val.copy()
    val_horizon["horizon"] = (val_horizon[DATE] - val_horizon[DATE].min()).dt.days + 1
    error_slices: JsonDict = {
        "horizon": blending.grouped_rmsle(
            val_blend, val_horizon, "horizon", worst=prepared.spec.horizon
        )
    }
    if "family" in split.val.columns:
        error_slices["family"] = blending.grouped_rmsle(val_blend, split.val, "family")
    val_preds["blend"] = val_blend
    test_preds["blend"] = test_blend
    write_preds(out_dir, val_preds, test_preds)
    source["models"] = models_meta
    source["error_slices"] = error_slices
    source["kaggle_ready"] = prepared.source == "kaggle"
    (out_dir / "result.json").write_text(
        json.dumps(source, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_status(out_dir, "done", "完了", 100)
    return source
