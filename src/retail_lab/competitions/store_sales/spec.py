"""このコンペが何を当てるか。画面の見出しもここから来る。"""

from __future__ import annotations

from retail_lab.competition import CompetitionSpec

SPEC = CompetitionSpec(
    slug="store-sales",
    title="Store Sales — Time Series Forecasting",
    kaggle_slug="store-sales-time-series-forecasting",
    required_files=(
        "train.csv",
        "test.csv",
        "stores.csv",
        "oil.csv",
        "holidays_events.csv",
        "transactions.csv",
    ),
    horizon=16,
    unit="店舗 × 商品ファミリー",
    target_label="日次売上",
    method=(
        {
            "id": "unit",
            "title": "予測単位",
            "body": "店 × 商品ファミリー × 日。テストは学習最終日の翌日から16日。",
        },
        {
            "id": "metric",
            "title": "指標",
            "body": "RMSLE。割合のずれで測るので、モデルも log1p(売上) を学習する。",
        },
        {
            "id": "lags",
            "title": "ラグの約束",
            "body": "16日先まで一度に出すので、売上ラグは16日以上だけ使う。未来漏洩を防ぐ。",
        },
        {
            "id": "blend",
            "title": "混ぜ方",
            "body": "学習末尾16日を検証に残し、RMSLE の逆数で重み付けする。",
        },
    ),
)
