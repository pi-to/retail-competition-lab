# Store Sales Lab

[Kaggle Store Sales — Time Series Forecasting](https://www.kaggle.com/competitions/store-sales-time-series-forecasting/data) を、後から人間が読み返せる4モデルで解く Web アプリです。

目標はリーダーボード上位と、その手順の理解です。手法の本文は [METHOD.md](METHOD.md) に5行で書いてあります。

## 何をするか

| モデル | 役割 |
| --- | --- |
| 季節ナイーブ | 同じ曜日の直近実績。下限 |
| LightGBM | プロモ・祝日・原油・給料日を店横断で学習 |
| Amazon Chronos-2 | 系列 + 未来共変量のゼロショット |
| Google TimesFM 2.5 | AWS に依らない単変量ゼロショット |
| 混合 | 検証 RMSLE の逆数重み + ゼロ系列の後処理 |

デモデータは公式と同じ列名の縮小セットです。公式 CSV を `data/kaggle/` に置けば提出用 `submission.csv` が出ます。

## 起動

```bash
python3 -m pip install -r requirements.txt
npm install
npm run dev
```

ブラウザで表示した画面の「予測を実行」を押します。初回は Hugging Face から Chronos-2 と TimesFM の重みを取ります。

CLI だけ使う場合:

```bash
python3 python/run.py --source demo
# 公式データ
python3 python/run.py --source kaggle
```

公式ファイル:

`train.csv` `test.csv` `stores.csv` `oil.csv` `holidays_events.csv` `transactions.csv` を `data/kaggle/` へ。

## なぜこの分け方か

基盤モデルは系列の形に強い一方、プロモの横断効果は表モデルの方が取りやすい、というのがこのコンペの要点です。同じ16日検証で数字を並べ、勝った側を多く使います。
