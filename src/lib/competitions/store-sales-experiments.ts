export type ExperimentInsight = {
  id: string;
  tag: string;
  title: string;
  localRmsle: number;
  leaderboard?: number;
  outcome: "採用" | "不採用" | "改善";
  tried: string;
  result: string;
  why: string;
  learned: string;
};

/**
 * 数字だけでは残らない体験を記録する。
 * 「なぜそう思うか」は事実と仮説を混同しないよう、仮説なら明記する。
 */
export const STORE_SALES_EXPERIMENTS: ExperimentInsight[] = [
  {
    id: "seasonal-naive",
    tag: "baseline-naive",
    title: "同じ曜日の直近をそのまま出す",
    localRmsle: 0.61704,
    outcome: "不採用",
    tried: "各店舗×商品ファミリーについて、同じ曜日の最後の売上を予測値にした。",
    result: "RMSLE 0.6170。高度なモデルが本当に必要かを判断する下限にはなった。",
    why: "曜日の周期は拾える一方、プロモーション、給料日、祝日、取扱終了を区別できないためと考える。",
    learned: "どんな高度なモデルも、まずこの数字を下回る必要がある。比較の物差しとして残す。",
  },
  {
    id: "direct-lightgbm",
    tag: "direct-lgbm",
    title: "16日先を一括でLightGBM予測",
    localRmsle: 0.43653,
    outcome: "不採用",
    tried: "ラグ16日以上、移動平均、プロモ、祝日、原油、店舗属性を1つのLightGBMで横断学習した。",
    result: "RMSLE 0.4365。ナイーブより大幅に良いが、Chronos-2には届かなかった。",
    why: "未来漏洩を避けるため直近1・7・14日の売上を使えず、強い週次パターンを捨てた影響が大きいと推測する。",
    learned: "表形式の外生変数は効く。次は1日ずつ進める再帰予測で近いラグを安全に使う。",
  },
  {
    id: "timesfm-only",
    tag: "timesfm-zero-shot",
    title: "Google TimesFM 2.5をゼロショット利用",
    localRmsle: 0.46438,
    outcome: "不採用",
    tried: "各系列の直近512日だけをTimesFMへ渡し、学習なしで16日を予測した。",
    result: "RMSLE 0.4644。LightGBMとChronos-2の両方に負け、最終混合の重みは0になった。",
    why: "この実装では売上系列しか渡しておらず、プロモーションや祝日の予定を見られないことが弱点と考える。",
    learned: "基盤モデルという理由だけで混ぜない。同じ検証窓で価値が確認できなければ重み0にする。",
  },
  {
    id: "chronos-full-context",
    tag: "chronos-long-context",
    title: "Chronos-2へ全期間を渡す",
    localRmsle: 0.4136,
    outcome: "不採用",
    tried: "Chronos-2へ利用可能な長い履歴をそのまま渡した。",
    result: "RMSLE 0.4136。推論にも約17分かかった。",
    why: "2013年の古い需要構造や地震など、現在と異なる局面まで参照して直近のパターンが薄まった可能性がある。",
    learned: "長い文脈が常に良いとは限らない。直近540日に絞ると0.4048へ改善し、約6分半に短縮した。",
  },
  {
    id: "inverse-score-blend",
    tag: "blend-inverse-rmsle",
    title: "RMSLEの逆数で単純に混ぜる",
    localRmsle: 0.42822,
    outcome: "不採用",
    tried: "各モデルの1/RMSLEを重みにして予測を平均した。",
    result: "RMSLE 0.4282。Chronos-2単体の0.4048より悪化した。",
    why: "相対順位しか見ない規則なので、弱いモデルにも必ず正の重みが付き、Chronos-2の良い予測を薄めた。",
    learned: "アンサンブルは自動的に強くならない。重み自体も検証で最適化し、単体にも負けるなら混ぜない。",
  },
  {
    id: "zero-21",
    tag: "zero-window-21",
    title: "直近21日ゼロの系列を強制的に0にする",
    localRmsle: 0.41187,
    outcome: "不採用",
    tried: "直近21日の売上合計が0なら、取扱終了とみなして予測を0へ置換した。",
    result: "Chronos-2単体0.4048から0.4119へ悪化した。",
    why: "一時的に売れていないだけの系列まで取扱終了と誤認し、その後の実売を0と予測したためと考える。",
    learned: "後処理も固定ルールにしない。0・3・7・14・21日を検証し、今回は『処理なし』を採用した。",
  },
  {
    id: "recursive-lgbm-v1",
    tag: "champion / latest",
    title: "商品ファミリー別の再帰LightGBMを追加",
    localRmsle: 0.3902,
    outcome: "改善",
    tried: "33商品ファミリーごとにLightGBMを学習し、予測を1日ずつ履歴へ戻して1・7・14日前のラグを安全に使った。",
    result: "再帰モデル単体0.3966。Chronos-2 37%、再帰LightGBM 58%、一括LightGBM 5%の混合で0.3902。旧Championを0.0098改善した。",
    why: "このデータの強い7日周期を、一括予測では捨てていた。再帰により直近週の形を使えたことが改善要因と考える。",
    learned: "公開解法で大きかった改善が自分の検証でも再現した。次は公開LBで再現性を確認し、ファミリー別のハイパーパラメータを調整する。",
  },
  {
    id: "foundation-blend-v1",
    tag: "baseline / champion",
    title: "Chronos-2 74% + LightGBM 26%",
    localRmsle: 0.40002,
    leaderboard: 0.39515,
    outcome: "採用",
    tried: "Chronos-2を直近540日に絞り、LightGBMとlog空間の非負最小二乗で混ぜた。",
    result: "ローカル0.4000、公開LB 0.39515。差は0.005で、ローカル検証が本番をよく再現した。",
    why: "Chronos-2が系列形状と未来共変量を捉え、LightGBMが店舗・商品カテゴリの横断効果を補ったと考える。",
    learned: "末尾16日の時系列検証を改善判断に使える。これを壊さず、再帰モデルを次の候補として加える。",
  },
];
