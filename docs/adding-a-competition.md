# コンペを1つ足す手順

小売の需要予測なら、共通部分（検証の切り方・指標・モデル・混合・レポート）はそのまま使える。
足すのはデータの読み込みと特徴だけ。

## 1. Python 側

`src/retail_lab/competitions/<slug>/` を作り、4つのファイルを置く。

| ファイル | 役割 |
| --- | --- |
| `spec.py` | slug・Kaggle slug・必要CSV・予測期間・予測単位 |
| `data.py` | CSV の読み込み。無ければ Kaggle から取得 |
| `demo.py` | 公式と同じ列名の縮小データ。認証なしで動かすため |
| `features.py` | パネル（1枚の表）と特徴の一覧を作る |
| `__init__.py` | `SPEC` と `prepare(root, source)` を公開 |

`prepare()` が返す `Prepared` の中身が共通部分との接点になる。

```python
Prepared(
    spec=SPEC,
    source=source,
    panel=panel,  # 学習行と提出行を縦に積んだ表
    features=[...],  # LightGBM に渡す列
    categoricals=[...],  # そのうちカテゴリ扱いする列
    covariates=[...],  # 未来でも値が分かる列（Chronos-2 に渡す）
)
```

`panel` が満たすべき列は4つだけ。

- `series_id`: 予測単位（店 × 商品など）
- `date`: 日付
- `target`: 当てたい数量。提出行は欠損にする
- `row_id`: 提出ファイルの id

売上ラグなどは `panel` を作る時点で計算しておく。予測期間より短いラグは使わない（未来漏洩になる）。

最後に `src/retail_lab/registry.py` の `_MODULES` にモジュールを足す。

## 2. 画面側

`src/lib/competitions/<slug>.ts` に説明文を書き、`src/lib/competitions/index.ts` の一覧に足す。
文章はここだけを直せば、概要・指標の説明・スコアの目安がすべて入れ替わる。

`src/lib/kaggle-status.ts` の `KAGGLE_SLUG` と `REQUIRED` にも同じ slug を足す。

## 3. 置き場所

| 種類 | 場所 |
| --- | --- |
| 公式データ | `data/<slug>/kaggle/`（git 管理外） |
| デモデータ | `data/<slug>/demo/`（git 追跡） |
| 実験結果と提出 | `outputs/<slug>/`（git 管理外） |
| 手法メモ | `docs/<slug>/method.md` |

## 4. 確認

```bash
uv run retail-lab list
uv run retail-lab --competition <slug> run --source demo
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

テストは `tests/` に足す。指標や分割のような共通部分を触ったときは、必ずテストを先に書く。
