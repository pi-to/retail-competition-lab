export type SubmitAction =
  | "submit_now"
  | "already_submitted"
  | "do_not_submit"
  | "superseded";

export type ExperimentInsight = {
  id: string;
  tag: string;
  title: string;
  /** 専門語なしの一言。表に出すのはこれだけ。 */
  plain: string;
  localRmsle: number;
  /** 重みを当てはめていない系列で採点した点数。Run同士の比較はこれで行う。 */
  holdoutRmsle?: number;
  leaderboard?: number;
  outcome: "採用" | "不採用" | "改善";
  submitAction: SubmitAction;
  runId?: string;
  tried: string;
  result: string;
  why: string;
  learned: string;
};

export const SUBMIT_LABEL: Record<SubmitAction, string> = {
  submit_now: "次に提出する",
  already_submitted: "提出済み",
  do_not_submit: "出さない",
  superseded: "負けたので保留",
};

/**
 * 数字だけでは残らない体験を記録する。
 * 「なぜそう思うか」は事実と仮説を混同しないよう、仮説なら明記する。
 * 提出判断は1行だけ `submit_now`。公開LBがある行は `already_submitted`。
 */
export const STORE_SALES_EXPERIMENTS: ExperimentInsight[] = [
  {
    id: "seasonal-naive",
    tag: "baseline-naive",
    title: "同じ曜日の直近をそのまま出す",
    plain: "先週の同じ曜日と同じだけ売れると考えた。比べるための下限。",
    localRmsle: 0.61704,
    outcome: "不採用",
    submitAction: "do_not_submit",
    tried: "各店舗×商品ファミリーについて、同じ曜日の最後の売上を予測値にした。",
    result: "RMSLE 0.6170。高度なモデルが本当に必要かを判断する下限にはなった。",
    why: "曜日の周期は拾える一方、プロモーション、給料日、祝日、取扱終了を区別できないためと考える。",
    learned: "どんな高度なモデルも、まずこの数字を下回る必要がある。比較の物差しとして残す。",
  },
  {
    id: "direct-lightgbm",
    tag: "direct-lgbm",
    title: "16日先を一括でLightGBM予測",
    plain: "表計算のような機械学習1本。特売や祝日は読めるが、直前の売れ方が使えない。",
    localRmsle: 0.43653,
    outcome: "不採用",
    submitAction: "do_not_submit",
    tried: "ラグ16日以上、移動平均、プロモ、祝日、原油、店舗属性を1つのLightGBMで横断学習した。",
    result: "RMSLE 0.4365。ナイーブより大幅に良いが、Chronos-2には届かなかった。",
    why: "未来漏洩を避けるため直近1・7・14日の売上を使えず、強い週次パターンを捨てた影響が大きいと推測する。",
    learned: "表形式の外生変数は効く。次は1日ずつ進める再帰予測で近いラグを安全に使う。",
  },
  {
    id: "timesfm-only",
    tag: "timesfm-zero-shot",
    title: "Google TimesFM 2.5をゼロショット利用",
    plain: "Googleの汎用予測モデルに売上の並びだけ渡した。特売を知らないので弱い。",
    localRmsle: 0.46438,
    outcome: "不採用",
    submitAction: "do_not_submit",
    tried: "各系列の直近512日だけをTimesFMへ渡し、学習なしで16日を予測した。",
    result: "RMSLE 0.4644。LightGBMとChronos-2の両方に負け、最終混合の重みは0になった。",
    why: "この実装では売上系列しか渡しておらず、プロモーションや祝日の予定を見られないことが弱点と考える。",
    learned: "基盤モデルという理由だけで混ぜない。同じ検証窓で価値が確認できなければ重み0にする。",
  },
  {
    id: "chronos-full-context",
    tag: "chronos-long-context",
    title: "Chronos-2へ全期間を渡す",
    plain: "AWSの汎用予測モデルに4年半すべて見せた。古い時代まで引きずって精度が落ちた。",
    localRmsle: 0.4136,
    outcome: "不採用",
    submitAction: "do_not_submit",
    tried: "Chronos-2へ利用可能な長い履歴をそのまま渡した。",
    result: "RMSLE 0.4136。推論にも約17分かかった。",
    why: "2013年の古い需要構造や地震など、現在と異なる局面まで参照して直近のパターンが薄まった可能性がある。",
    learned: "長い文脈が常に良いとは限らない。直近540日に絞ると0.4048へ改善し、約6分半に短縮した。",
  },
  {
    id: "inverse-score-blend",
    tag: "blend-inverse-rmsle",
    title: "RMSLEの逆数で単純に混ぜる",
    plain: "成績の良さに応じて自動で混ぜた。弱いモデルも必ず入るので悪化。",
    localRmsle: 0.42822,
    outcome: "不採用",
    submitAction: "do_not_submit",
    tried: "各モデルの1/RMSLEを重みにして予測を平均した。",
    result: "RMSLE 0.4282。Chronos-2単体の0.4048より悪化した。",
    why: "相対順位しか見ない規則なので、弱いモデルにも必ず正の重みが付き、Chronos-2の良い予測を薄めた。",
    learned: "アンサンブルは自動的に強くならない。重み自体も検証で最適化し、単体にも負けるなら混ぜない。",
  },
  {
    id: "zero-21",
    tag: "zero-window-21",
    title: "直近21日ゼロの系列を強制的に0にする",
    plain: "3週間売れていない棚は「もう置いていない」と決め打ちした。休んでいただけの棚を潰した。",
    localRmsle: 0.41187,
    outcome: "不採用",
    submitAction: "do_not_submit",
    tried: "直近21日の売上合計が0なら、取扱終了とみなして予測を0へ置換した。",
    result: "Chronos-2単体0.4048から0.4119へ悪化した。",
    why: "一時的に売れていないだけの系列まで取扱終了と誤認し、その後の実売を0と予測したためと考える。",
    learned: "後処理も固定ルールにしない。0・3・7・14・21日を検証し、今回は『処理なし』を採用した。",
  },
  {
    id: "recursive-lgbm-v1",
    tag: "superseded",
    title: "商品ファミリー別の再帰LightGBMを追加",
    plain: "売り場ごとにモデルを分け、1日ずつ予測を積み上げた。週のリズムが効いた。",
    localRmsle: 0.3902,
    outcome: "改善",
    submitAction: "superseded",
    tried: "33商品ファミリーごとにLightGBMを学習し、予測を1日ずつ履歴へ戻して1・7・14日前のラグを安全に使った。",
    result: "再帰モデル単体0.3966。Chronos-2 37%、再帰LightGBM 58%、一括LightGBM 5%の混合で0.3902。当時のChampionを0.0098改善した。",
    why: "このデータの強い7日周期を、一括予測では捨てていた。再帰により直近週の形を使えたことが改善要因と考える。",
    learned: "公開解法で大きかった改善が自分の検証でも再現した。その後、木数と外生変数でさらに下がったため提出対象からは外す。",
  },
  {
    id: "recursive-trees-320",
    tag: "recursive-320",
    title: "再帰LightGBMの木を320本にする",
    plain: "モデルの細かさと参照する過去の長さを振って選んだ。",
    localRmsle: 0.39584,
    outcome: "改善",
    submitAction: "superseded",
    tried: "同じ末尾16日検証で、木の本数と学習期間だけを変えた。",
    result: "320本・730日で単体0.39584。140本は0.39884、365日は0.40232、1095日は0.40030。",
    why: "木を増やすと週次ラグを細かく拾える一方、古い履歴を足すと地震や古い需要が混ざる、という仮説。",
    learned: "Chronos-2と同じく、長い履歴は自動では良くならない。採用は混合後の数字で決める。単体では出さない。",
  },
  {
    id: "direct-horizon-lgbm",
    tag: "direct-horizon",
    title: "予測距離に応じた直近ラグで一括予測する",
    plain: "「何日先か」に応じて使える実績を選び、積み上げをやめた版。単体では負ける。",
    localRmsle: 0.41756,
    outcome: "不採用",
    submitAction: "do_not_submit",
    tried: "h日先の予測にはh日以上前の売上だけを使い、予測を履歴へ戻さず16日を一括で出した。",
    result: "単体RMSLE 0.41756。再帰0.39584より悪い。",
    why: "誤差の連鎖は避けられるが、lag_1を毎日同じ形で使えない損失の方が大きかったと考える。",
    learned: "漏洩しない近いラグでも、再帰のフィードバックを完全に捨てると週次の形が弱くなる。混合候補としては残す。単体では出さない。",
  },
  {
    id: "recursive320-direct-horizon-v1",
    tag: "superseded",
    title: "320本の再帰と予測距離別モデルを混ぜる",
    plain: "積み上げ型と一括型を混ぜた。外れ方が違うので補い合った。",
    localRmsle: 0.38893,
    outcome: "改善",
    submitAction: "superseded",
    tried: "再帰LightGBMを320本にし、予測距離別LightGBMを混合候補へ足した。Chronos-2とTimesFMは同じ検証窓のまま。",
    result: "混合RMSLE 0.38893。重みは再帰53%、Chronos-2 33%、距離別13%。一括LightGBMとTimesFMは0。提出CSVはヘッダ+28512行。",
    why: "距離別モデルは単体では再帰に負けるが、誤差の連鎖がない日の予測がChronos-2や再帰と補い合ったため、検証の非負最小二乗が正の重みを付けたと考える。",
    learned: "単体で負けても、違う外れ方なら混ぜて良くなる。祝日・プロモと地震除外でさらに下がったので、このCSVは出さない。",
  },
  {
    id: "exog-holiday-promo-v1",
    tag: "superseded",
    title: "地域祝日・前夜・プロモ先行を足す",
    plain: "地域の祝日、祝日前夜、特売の前後をカレンダーとして渡した。",
    localRmsle: 0.3859,
    outcome: "改善",
    submitAction: "superseded",
    runId: "20260916-110352-exog-holiday-promo-v1-44e366",
    tried: "地域祝日、祝日前夜、祝日までの日数、プロモの1・7日前と1・7日後を特徴に足し、Chronos-2へ地元・地域・前夜も渡した。売上ラグは増やしていない。",
    result: "混合RMSLE 0.3859。再帰0.39267、一括LightGBM 0.41844、距離別0.41342、Chronos-2 0.40401。重みは再帰51%、Chronos-2 30%、一括11%、距離別8%。",
    why: "検証窓と提出窓の両方に祝日があり、プロモは提出CSVに未来分が載っている。既知の外生変数を捨てていたのがボトルネックだったと考える。",
    learned: "未来漏洩にならない情報は先に使い切る。地震期間除外で 0.00006 だけ勝ったので、こちらはロールバック用に残す。",
  },
  {
    id: "exog-no-eq-v1",
    tag: "previous-champion",
    title: "地震期間を学習から外して混ぜる",
    plain: "2016年の地震直後の異常な売上を、教える材料から外した。",
    localRmsle: 0.38584,
    outcome: "改善",
    submitAction: "superseded",
    runId: "20260916-111927-exog-no-eq-v1-bc157d",
    tried: "祝日・プロモ特徴はそのまま、再帰LightGBMの学習だけ 2016-04-16〜05-31 を外した（検証・提出の予測対象は変えていない）。",
    result: "混合RMSLE 0.38584。no_eq 単体は 0.3941 だが混合で 11% の重み。Champion CSV はこのRun。公開LBは未記録。",
    why: "地震直後の特需は通常の16日予測と形が違う、という仮説。単体は悪化しても、他モデルと外れ方が違うため混ぜるとわずかに下がった。",
    learned: "学習から外す対照は『単体が良くなるか』ではなく『混合が良くなるか』で決める。グローバル混合としてはここまで。次は系統ごとの重み。",
  },
  {
    id: "horizon-family-blend-v1",
    tag: "previous-champion",
    title: "商品ファミリーごとに混ぜ方を変える",
    plain: "売り場ごとに得意なモデルが違うので、混ぜる比率を売り場別にした。",
    localRmsle: 0.3755,
    outcome: "改善",
    submitAction: "superseded",
    runId: "20260916-114328-horizon-family-blend-v1-05fe40",
    tried: "Championの保存済み予測だけを読み、混ぜ方の候補に『全体1組』『予測日ごと』『商品ファミリーごと』を入れて検証窓で選んだ。モデルの再学習はしていない。",
    result: "ファミリー別 0.3755 が採用。日別 0.38089、全体 0.38584。LINGERIE は 0.639→0.622、SCHOOL AND OFFICE SUPPLIES は 0.578→0.517。提出CSVはヘッダ+28,512行。公開LBは未記録。",
    why: "系統によって当たるモデルが違う。LINGERIEは距離別と一括LightGBM、GROCERY IIは距離別とTimesFM、学用品は再帰が厚い。1組の重みでは平均に潰れていたと考える。",
    learned: "日×系統の重みは同じ検証窓で 0.356 まで下がるが、パラメータが多すぎて過学習の疑いがあるので採用しない。間欠需要のモデルを足すのが次。",
  },
  {
    id: "sparse-recursive-v1",
    tag: "superseded",
    title: "短い履歴とTweedie再帰を混ぜる",
    plain: "売れない日が多い売り場（下着など）向けのモデルを足した。",
    localRmsle: 0.37441,
    outcome: "改善",
    submitAction: "superseded",
    runId: "20260916-120915-sparse-recursive-v1-ac0596",
    tried: "再帰LightGBMに直近180日版と、Tweedie目的・365日版を追加。既存モデルと一緒にファミリー別混合した。Chronos/TimesFMは前回Runを再利用。",
    result: "混合RMSLE 0.37441。LINGERIEは 0.622→0.617（重みの約39%がTweedie）。SCHOOL AND OFFICE SUPPLIESは 0.517→0.511。提出CSVはヘッダ+28,512行。公開LBは未記録。",
    why: "LINGERIEはゼロが多く log1p 再帰が過小予測していた。Tweedieはゼロ込みの売上分布に合い、短い履歴は古い需要を捨てる。単体では両方とも全体スコアを悪化させるが、系統ごとに混ぜると効く。",
    learned: "悪い系統用のモデルは全体一位にならなくてよい。ファミリー別混合の候補として足せばよい。GROCERY II はまだ過大予測が残る。",
  },
  {
    id: "robust-min-family-v1",
    tag: "superseded",
    title: "過大予測を行ごと最小で抑える",
    plain: "多めに出がちな売り場は、候補のうち一番控えめな数字を採った。",
    localRmsle: 0.374,
    holdoutRmsle: 0.38157,
    outcome: "改善",
    submitAction: "superseded",
    runId: "20260916-121346-robust-min-family-v1-8f95f3",
    tried: "direct・再帰・再帰(地震除外)・TimesFMの予測を行ごとに最小値でまとめた robust_min を候補に足し、ファミリー別混合し直した。再学習なし。",
    result: "混合RMSLE 0.37400（前Champion 0.37441）。GROCERY II の系統で robust_min が正の重みを持つ。提出CSVはヘッダ+28,512行。公開LBは未記録。",
    why: "GROCERY II は検証窓で売上が上がり、各モデルが上に外れやすい。行ごと最小は一番控えめな候補を残し、過大予測の罰を減らす。",
    learned: "後段のまとめ方もモデル候補として検証に載せる。単体 0.47 でも混ぜれば効く。ただし後述のとおり、この 0.374 は重みを当てはめた行で測った点数で、甘く出ていた。",
  },
  {
    id: "honest-selection-v1",
    tag: "method-fix",
    title: "重みを当てはめた行で選ぶのをやめる",
    plain: "採点の仕方が甘かったので、重みを決めていない店舗で採点するように直した。",
    localRmsle: 0.37559,
    holdoutRmsle: 0.38061,
    outcome: "改善",
    submitAction: "superseded",
    runId: "20260916-124435-honest-family-blend-v1-5bbaa1",
    tried: "ファミリーごとに系列（店舗）を2つに割り、片方で重みを当てはめ、もう片方で採点。両方向の平均で混ぜ方・ゼロ窓・縮約率を選ぶようにした。過去Runにも同じ物差しを後入れ（rescore）。",
    result: "この物差しで測ると、直前Championの 0.374 は 0.38157、その前の版は 0.38061 で、実は悪化していた。縮約率0.85のファミリー別混合が 0.38061 で最良。",
    why: "ファミリー別の重みは、重みを当てはめたその行では必ず有利に見える。似たモデルを並べるほど当てはめ過ぎる。見ていない店舗で採点すると、その下駄が外れる。",
    learned: "改善かどうかは、当てはめに使っていないデータで測る。Champion昇格の判定もこの点数に切り替えた。",
  },
  {
    id: "honest-subset-blend-v1",
    tag: "champion / latest",
    title: "足を引っ張るモデルを外す",
    plain: "混ぜる顔ぶれを見直し、見ていない店舗で悪化させる5モデルを外した。",
    localRmsle: 0.37581,
    holdoutRmsle: 0.38027,
    outcome: "改善",
    submitAction: "submit_now",
    runId: "20260916-125014-honest-subset-blend-v1-301513",
    tried: "10候補から1つずつ外し、見ていない店舗の点数が良くなる限り落とした。Tweedie再帰、一括LightGBM、季節ナイーブ、地震除外再帰、TimesFMが落ちた。",
    result: "残ったのは Chronos-2・予測距離別・再帰・短い履歴再帰・行ごと最小の5つで 0.38027（前 0.38061）。提出CSVはヘッダ+28,512行。公開LBは未記録。",
    why: "似た予測を並べると、重みの当てはめがその重複に反応してしまう。数を絞ると重みが安定し、未知の系列でも崩れにくい。",
    learned: "モデルは足すだけでなく、外す判断も検証に任せる。次は残った5つの中身（LINGERIE 0.623、GROCERY II 0.571）を改善する。",
  },
  {
    id: "foundation-blend-v1",
    tag: "baseline",
    title: "Chronos-2 74% + LightGBM 26%",
    plain: "最初にKaggleへ出した版。ここだけ本番の点数が分かっている。",
    localRmsle: 0.40002,
    leaderboard: 0.39515,
    outcome: "採用",
    submitAction: "already_submitted",
    tried: "Chronos-2を直近540日に絞り、LightGBMとlog空間の非負最小二乗で混ぜた。",
    result: "ローカル0.4000、公開LB 0.39515。差は0.005で、ローカル検証が本番をよく再現した。",
    why: "Chronos-2が系列形状と未来共変量を捉え、LightGBMが店舗・商品カテゴリの横断効果を補ったと考える。",
    learned: "末尾16日の時系列検証を改善判断に使える。公開LBがあるのはこの行だけ。次の提出はこれより良いChampionにする。",
  },
];

export type SubmitRecommendation = {
  experiment: ExperimentInsight;
  headline: string;
  whyThis: string;
  doNotSubmit: string;
};

/** 比較に使う点数。隠して採点した点数があればそれを優先する。 */
export function comparableScore(item: ExperimentInsight): number {
  return item.holdoutRmsle ?? item.localRmsle;
}

export function pickSubmitCandidate(
  experiments: ExperimentInsight[] = STORE_SALES_EXPERIMENTS
): ExperimentInsight {
  const marked = experiments.find((item) => item.submitAction === "submit_now");
  if (marked) return marked;
  return [...experiments].sort((a, b) => comparableScore(a) - comparableScore(b))[0];
}

export function submitRecommendation(
  experiments: ExperimentInsight[] = STORE_SALES_EXPERIMENTS
): SubmitRecommendation {
  const experiment = pickSubmitCandidate(experiments);
  const submitted = experiments.find((item) => item.submitAction === "already_submitted");
  const score = comparableScore(experiment);
  return {
    experiment,
    headline: `提出するのは「${experiment.title}」（模擬試験 ${score.toFixed(5)}）`,
    whyThis:
      "重みを決めていない店舗で採点した点数がいちばん低いRun。提出CSV（ヘッダ+28,512行）もこの成果物です。公開LBは未記録なので、次にKaggleへ出すならこれ1本。",
    doNotSubmit: submitted
      ? `公開LB ${submitted.leaderboard?.toFixed(5)} の「${submitted.title}」は提出済みの古い混合（ローカル ${submitted.localRmsle.toFixed(5)}）。同じCSVを出し直さない。灰色の「出さない」は単体・失敗実験。`
      : "失敗実験と単体スコアは出さない。混ぜたChampionだけ出す。",
  };
}

export function experimentsByScore(
  experiments: ExperimentInsight[] = STORE_SALES_EXPERIMENTS
): ExperimentInsight[] {
  return [...experiments].sort((a, b) => comparableScore(a) - comparableScore(b));
}
