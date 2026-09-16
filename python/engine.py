from __future__ import annotations

import json
import time
import traceback
from pathlib import Path

import pandas as pd

import blend as blend_mod
import models_chronos
import models_lgbm
import models_naive
import models_timesfm
from data import HORIZON, load_bundle, split_holdout
from status import write_status

METHOD = [
    {
        "id": "unit",
        "title": "予測単位",
        "body": "店 × 商品ファミリー × 日。テストは学習最終日の翌日から16日。",
    },
    {
        "id": "metric",
        "title": "指標",
        "body": "RMSLE。大きい店の誤差が支配しないよう log1p で測る。モデルも log1p(sales) を学習する。",
    },
    {
        "id": "roles",
        "title": "役割分担",
        "body": "季節ナイーブ＝下限。LightGBM＝プロモ・祝日・原油・店属性を横断学習。Chronos-2＝系列の形と未来共変量。TimesFM＝AWSに依らない系列の形。",
    },
    {
        "id": "lags",
        "title": "ラグの約束",
        "body": "16日先まで一度に出すので、売上ラグは16日以上だけ使う。未来漏洩を防ぐ。",
    },
    {
        "id": "blend",
        "title": "混ぜ方",
        "body": "学習末尾16日を検証に残し、RMSLEの逆数で重み付け。効いたモデルほど多く使う。",
    },
]


def _json_ready(pred: pd.DataFrame) -> list[dict]:
    rows = pred.copy()
    rows["date"] = rows["date"].dt.strftime("%Y-%m-%d")
    return rows.round(4).to_dict(orient="records")


def _preview(history: pd.DataFrame, val: pd.DataFrame, pred_map: dict[str, pd.DataFrame], blend_df: pd.DataFrame) -> dict:
    totals = history.groupby("series_id")["sales"].sum().sort_values(ascending=False)
    sid = str(totals.index[0])
    hist = history[history["series_id"] == sid].sort_values("date").tail(42)
    actual = val[val["series_id"] == sid].sort_values("date")
    series = {
        "series_id": sid,
        "history": [
            {"date": d.strftime("%Y-%m-%d"), "sales": float(s)}
            for d, s in zip(hist["date"], hist["sales"])
        ],
        "actual": [
            {"date": d.strftime("%Y-%m-%d"), "sales": float(s)}
            for d, s in zip(actual["date"], actual["sales"])
        ],
        "models": {},
    }
    for name, df in {**pred_map, "blend": blend_df}.items():
        sub = df[df["series_id"] == sid].sort_values("date")
        series["models"][name] = [
            {"date": d.strftime("%Y-%m-%d"), "pred": float(p)}
            for d, p in zip(sub["date"], sub["pred"])
        ]
    return series


def run(root: Path, source: str, out_dir: Path, skip_foundation: bool = False) -> dict:
    t0 = time.time()
    out_dir.mkdir(parents=True, exist_ok=True)
    write_status(out_dir, "load", "データを読み込みます", 5)
    bundle = load_bundle(root, source)
    from data import add_series_id

    train = add_series_id(bundle.train)
    test = add_series_id(bundle.test)
    hist, val = split_holdout(train, HORIZON)
    n_series = int(train["series_id"].nunique())

    models_meta: list[dict] = []
    val_preds: dict[str, pd.DataFrame] = {}
    test_preds: dict[str, pd.DataFrame] = {}
    scores: dict[str, float] = {}
    importance: list[dict] = []

    def register(model_id: str, title: str, note: str, val_df: pd.DataFrame, test_df: pd.DataFrame, extra: dict | None = None) -> None:
        sc = blend_mod.score_against(val_df, val)
        scores[model_id] = sc
        val_preds[model_id] = val_df
        test_preds[model_id] = test_df
        row = {"id": model_id, "title": title, "note": note, "rmsle": round(sc, 5), "status": "ok"}
        if extra:
            row.update(extra)
        models_meta.append(row)

    write_status(out_dir, "naive", "季節ナイーブ（同じ曜日の直近）", 15)
    register(
        "seasonal_naive",
        "季節ナイーブ",
        "同じ曜日の最後の実績。下限。これを大きく下回れない手法は捨てる。",
        models_naive.seasonal_naive(hist, val),
        models_naive.seasonal_naive(train, test),
    )

    write_status(out_dir, "lgbm", "LightGBM（横断表）", 30)
    val_lgb, importance = models_lgbm.fit_predict(hist, val, bundle.stores, bundle.oil, bundle.holidays)
    test_lgb, importance_full = models_lgbm.fit_predict(train, test, bundle.stores, bundle.oil, bundle.holidays)
    importance = importance_full
    register(
        "lightgbm",
        "LightGBM",
        "ラグ16日以上 + プロモ + 祝日 + 原油 + 給料日 + 店属性。log1p 学習。",
        val_lgb,
        test_lgb,
        {"top_features": importance[:8]},
    )

    if not skip_foundation:
        try:
            write_status(out_dir, "chronos", "Amazon Chronos-2（共変量つきゼロショット）", 50)
            chronos_pipe = models_chronos.load_pipeline()
            register(
                "chronos2",
                "Chronos-2",
                "AWS の時系列基盤モデル。売上系列にプロモ・祝日・原油・給料日を渡す。学習しない。",
                models_chronos.forecast(hist, val, bundle.stores, bundle.oil, bundle.holidays, HORIZON, pipe=chronos_pipe),
                models_chronos.forecast(train, test, bundle.stores, bundle.oil, bundle.holidays, HORIZON, pipe=chronos_pipe),
                {"checkpoint": models_chronos.CHECKPOINT, "org": "Amazon"},
            )
            del chronos_pipe
        except Exception as exc:
            models_meta.append(
                {
                    "id": "chronos2",
                    "title": "Chronos-2",
                    "note": "読み込みまたは推論に失敗",
                    "status": "skipped",
                    "error": f"{exc}",
                    "checkpoint": models_chronos.CHECKPOINT,
                    "org": "Amazon",
                }
            )
            (out_dir / "chronos_error.txt").write_text(traceback.format_exc(), encoding="utf-8")

        try:
            write_status(out_dir, "timesfm", "Google TimesFM 2.5（単変量ゼロショット）", 75)
            tfm = models_timesfm.load_model()
            register(
                "timesfm",
                "TimesFM 2.5",
                "Google の時系列基盤モデル。売上の数値列だけを読む。AWS に依存しない対照実験。",
                models_timesfm.forecast(hist, val, HORIZON, model=tfm),
                models_timesfm.forecast(train, test, HORIZON, model=tfm),
                {"checkpoint": models_timesfm.CHECKPOINT, "org": "Google"},
            )
            del tfm
        except Exception as exc:
            models_meta.append(
                {
                    "id": "timesfm",
                    "title": "TimesFM 2.5",
                    "note": "読み込みまたは推論に失敗",
                    "status": "skipped",
                    "error": f"{exc}",
                    "checkpoint": models_timesfm.CHECKPOINT,
                    "org": "Google",
                }
            )
            (out_dir / "timesfm_error.txt").write_text(traceback.format_exc(), encoding="utf-8")

    write_status(out_dir, "blend", "検証 RMSLE の逆数で混合", 90)
    weights = blend_mod.inverse_rmsle_weights(scores)
    val_blend = blend_mod.zero_sales_rule(hist, blend_mod.blend(val_preds, weights))
    test_blend = blend_mod.zero_sales_rule(train, blend_mod.blend(test_preds, weights))
    blend_rmsle = blend_mod.score_against(val_blend, val)

    for row in models_meta:
        if row.get("status") == "ok":
            row["weight"] = round(weights.get(row["id"], 0.0), 4)

    models_meta.append(
        {
            "id": "blend",
            "title": "混合 + ゼロ系列",
            "note": "逆RMSLE重み。直近21日がすべて0の系列は0のまま。",
            "rmsle": round(blend_rmsle, 5),
            "status": "ok",
            "weight": 1.0,
            "weights": {k: round(v, 4) for k, v in weights.items()},
        }
    )

    submission = test_blend[["id", "pred"]].rename(columns={"pred": "sales"}).sort_values("id")
    submission.to_csv(out_dir / "submission.csv", index=False)

    result = {
        "source": bundle.source,
        "horizon": HORIZON,
        "n_series": n_series,
        "n_train_rows": int(len(train)),
        "train_end": str(train["date"].max().date()),
        "test_start": str(test["date"].min().date()),
        "test_end": str(test["date"].max().date()),
        "metric": "RMSLE",
        "models": models_meta,
        "feature_importance": importance[:16],
        "preview": _preview(hist, val, val_preds, val_blend),
        "method": METHOD,
        "elapsed_sec": round(time.time() - t0, 1),
        "kaggle_ready": bundle.source == "kaggle",
    }
    (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    write_status(out_dir, "done", "完了", 100)
    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=["demo", "kaggle"], default="demo")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--skip-foundation", action="store_true")
    args = parser.parse_args()
    out = args.out or (args.root / "outputs")
    run(args.root, args.source, out, skip_foundation=args.skip_foundation)
