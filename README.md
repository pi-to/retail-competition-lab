# Retail Lab

小売の需要予測コンペを、手法が後から読める形で解くリポジトリです。いまは Kaggle の
[Store Sales — Time Series Forecasting](https://www.kaggle.com/competitions/store-sales-time-series-forecasting/data)
を扱っています。コンペを足すときは [docs/adding-a-competition.md](docs/adding-a-competition.md) を見てください。

## 何の問題か（Store Sales）

エクアドルの食品スーパー Favorita の発注担当が、店舗×商品ファミリーごとに16日先までの売上を毎日決めている。54店舗 × 33ファミリー = 1,782 系列 × 16日 = 28,512 個の予測が、そのまま発注量になる。少なく見れば欠品、多く見れば廃棄。両方を同時に減らすのが狙いです。

採点は RMSLE。なぜその指標が妥当かは [docs/store-sales/method.md](docs/store-sales/method.md) に具体例つきで書いてあります。

## 画面でできること

1. コンペの概要（誰が困り、何を当て、どう効くか）と指標の妥当性を読む。
2. 4モデルを同じ検証窓で走らせて採点する。
3. 検証結果を「誤差率・偏り・欠品側の割合」で読む（クライアント報告用）。
4. 提出内容を確認して、画面から Kaggle へ送る。

## モデル

| モデル | 役割 |
| --- | --- |
| 季節ナイーブ | 同じ曜日の直近実績。下限 |
| LightGBM | プロモ・祝日・原油・給料日・店属性を系列横断で学習 |
| Amazon Chronos-2 | 系列 + 未来共変量のゼロショット |
| Google TimesFM 2.5 | AWS に依らない単変量ゼロショット |
| 混合 | 検証 RMSLE の逆数重み + ゼロ系列の後処理 |

## 起動

Python は uv、画面は npm です。

```bash
uv sync --frozen
npm install
npm run dev
```

http://127.0.0.1:43123 が開きます。「予測を実行」でデモデータ（4店舗 × 6ファミリー）が採点されます。初回は Hugging Face から Chronos-2 と TimesFM の重みを取得します。

## コマンド

```bash
uv run retail-lab list                       # 登録済みのコンペ
uv run retail-lab status                     # 公式データの取得状況
uv run retail-lab fetch                      # Kaggle から公式データを取得
uv run retail-lab run --source demo          # デモデータで実験
uv run retail-lab run --source kaggle        # 公式データで実験（未取得なら自動取得）
uv run retail-lab submit --message "説明"      # 生成済みCSVを検査してKaggleへ提出
uv run retail-lab --competition store-sales run --source demo
```

## 公式データの取得

画面は取得操作を見せず、公式データが無ければ再計算時に API から自動取得します。
CLI から明示的に取る場合は `uv run retail-lab fetch` を使います。事前に2つ必要です。

1. コンペページで Join Competition（規約同意）。
2. Kaggle の [Settings](https://www.kaggle.com/settings) で API トークンを作る。

認証情報は次のいずれかで渡します。`.env.local` は Next.js が読み込み、Python にも渡ります。

```bash
# 新しい API トークン（KGAT_ で始まる）
KAGGLE_API_TOKEN=KGAT_xxxxxxxx

# 旧来の方式
KAGGLE_USERNAME=your_name
KAGGLE_KEY=your_key
```

`kaggle.json` をリポジトリ直下に置く方法でも動きます。

## 確認コマンド

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
npm run lint
```

## ファイル構成

```
src/retail_lab/            小売コンペ共通の土台
  metrics.py               RMSLE と、現場に説明する指標
  validation.py            検証窓の切り方
  blending.py              混合とゼロ系列の後処理
  experiment.py            実験ループ（全コンペ共通）
  kaggle.py                Kaggle API
  registry.py              扱っているコンペの一覧
  cli.py                   uv run retail-lab
  models/                  naive / gbdt / chronos / timesfm
  competitions/store_sales/  このコンペ固有のデータと特徴
src/app, src/components    画面（Next.js）
src/lib/competitions/      画面に出す説明文。コンペごとに1ファイル
data/<slug>/{demo,kaggle}  データ
outputs/<slug>/            結果と submission.csv
docs/                      手法メモとコンペ追加手順
tests/                     指標・分割・混合のテスト
```

`.env.local`、`kaggle.json`、`data/*/kaggle/`、`outputs/`、`.venv/` は git 管理外です。

## Kaggle への提出

提出にはコンペへの参加が必要です。未参加のまま提出すると Kaggle は
`Permission 'competitions.participate' was denied`（HTTP 403）を返します。

参加はアカウント単位です。ブラウザで参加していても、`KAGGLE_API_TOKEN` が別アカウントの
ものだと提出できません。`uv run retail-lab preflight` はトークンのアカウント名と参加状態を
表示するので、まずそこを合わせてください。

トークンは `.env.local` を直接読みます。差し替えたら、開発サーバーを再起動せずにそのまま
`preflight` や提出に反映されます。

参加済みで直らない場合は、電話番号認証の未完了、招待制コンペ、トークンの失効を順に確認します。

個人アクセストークン（`KGAT_`）の作成画面に権限の選択肢はありません。権限（スコープ）の指定は
OAuth アプリ向けの仕組みなので、提出のためにトークンを作り直す必要は通常ありません。

状態は先に確認できます。

```bash
uv run retail-lab preflight
```


画面の「提出内容を確認」から送れます。誤送信を防ぐため、1回目のクリックでは送信せず、
コンペ名・検証 RMSLE・提出行数・採用モデルとグラフを表示し、あわせて権限と参加状態を確認します。
「この内容でKaggleへ提出」を押した時だけ送信します。権限が足りない場合はボタンが無効になり、
トークン再作成・コンペ参加・CSVを落として手で提出する導線を出します。

送信前に次を自動検査します。

- 結果がデモではなく公式データ由来である
- 28,512行で、公式 `sample_submission.csv` とIDが完全に一致する
- IDの重複、売上の欠損・負数がない

Kaggle側の受付結果は `outputs/<slug>/last_submission.json` に保存します。
