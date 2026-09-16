"""小売の需要予測コンペで共通に使う道具。

コンペ固有の処理は `retail_lab.competitions.<slug>` に置く。
共通側が前提にしている列は次の4つだけ。

- ``series_id``: 予測単位（店 × 商品など）
- ``date``: 日付
- ``target``: 当てたい数量
- ``row_id``: 提出に使う行の識別子
"""

SERIES_ID = "series_id"
DATE = "date"
TARGET = "target"
ROW_ID = "row_id"
