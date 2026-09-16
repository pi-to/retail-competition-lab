# Store Sales Lab

[Kaggle Store Sales — Time Series Forecasting](https://www.kaggle.com/competitions/store-sales-time-series-forecasting/data) を、非エンジニアでも結果が読める形で解く Web アプリです。

## 何の問題か

エクアドルの食品スーパー Favorita の発注担当が、店舗×商品ファミリーごとに16日先までの売上を毎日決めている。54店舗 × 33ファミリー = 1,782 系列 × 16日 = 28,512 個の予測が、そのまま発注量になる。少なく見れば欠品、多く見れば廃棄。両方を同時に減らすのが狙いです。

採点は RMSLE。なぜその指標が妥当かは [METHOD.md](METHOD.md) に具体例つきで書いてあります。

## 画面でできること

1. コンペの概要（誰が困り、何を当て、どう効くか）と指標の妥当性を読む。
2. 公式データを Kaggle API から取得する。
3. 4モデルを同じ検証窓で走らせて採点する。
4. 検証結果を「誤差率・偏り・欠品側の割合」で読む（クライアント報告用）。
5. `submission.csv` をダウンロードする。

## モデル

| モデル | 役割 |
| --- | --- |
| 季節ナイーブ | 同じ曜日の直近実績。下限 |
| LightGBM | プロモ・祝日・原油・給料日・店属性を店横断で学習 |
| Amazon Chronos-2 | 系列 + 未来共変量のゼロショット |
| Google TimesFM 2.5 | AWS に依らない単変量ゼロショット |
| 混合 | 検証 RMSLE の逆数重み + ゼロ系列の後処理 |

## 起動

```bash
python3 -m pip install -r requirements.txt
npm install
npm run dev
```

http://127.0.0.1:43123 が開きます。「予測を実行」でデモデータ（4店舗 × 6ファミリー）が採点されます。初回は Hugging Face から Chronos-2 と TimesFM の重みを取得します。

## 公式データの取得

画面の「Kaggle から取得」を押すと API でダウンロードします。事前に2つ必要です。

1. コンペページで Join Competition（規約同意）。
2. Kaggle の [Settings](https://www.kaggle.com/settings) で API トークンを作る。

認証情報は次のどちらかで渡します。

```bash
# 方法1: .env.local に書く（Next.js が読み込み、Python にも渡る）
KAGGLE_USERNAME=your_name
KAGGLE_KEY=your_key
```

```bash
# 方法2: ダウンロードした kaggle.json をリポジトリ直下に置く
```

CLI だけで使う場合:

```bash
python3 python/kaggle_data.py --status   # 取得状況の確認
python3 python/kaggle_data.py            # ダウンロード
python3 python/run.py --source kaggle    # 公式データで実行（未取得なら自動取得）
python3 python/run.py --source demo      # デモデータで実行
```

`.env.local` と `kaggle.json`、`data/kaggle/`、`outputs/` は git 管理外です。

## テスト

```bash
cd python && python3 -m pytest -q   # 指標の性質（RMSLE が割合で罰することなど）
npm run lint
```

## ファイルの読み方

- `src/lib/overview.ts` — コンペ概要と指標の説明。文章はここだけ直せば画面と README が揃う。
- `python/engine.py` — 実験の流れ。上から読めば手順が分かる。
- `python/features.py` — 使っている特徴の全部。
- `python/models_*.py` — モデル1つにファイル1つ。
- `METHOD.md` — 手法と指標の妥当性のメモ。
