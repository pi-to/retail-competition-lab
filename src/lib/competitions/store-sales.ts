import type { CompetitionContent } from "@/lib/competitions/types";

/**
 * Kaggle Store Sales（Favorita / エクアドル）の説明。
 * 画面は短い文と図だけ。くわしい理屈は折りたたみへ。
 */
const storeSales: CompetitionContent = {
  slug: "store-sales",
  title: "Store Sales — Time Series Forecasting",
  headline: "スーパーの発注を、2週間先まで当てる",
  oneLine:
    "エクアドルの食品スーパー Favorita が、店ごと・商品ごとに「明日から16日間、何がどれだけ売れるか」を毎日当てたい。",
  badges: ["Kaggle Store Sales", "食品スーパーの需要予測", "16日先"],
  plain: {
    gist: "毎朝の発注を当てるコンテスト。当たれば品切れと廃棄が同時に減る。",
    cards: [
      {
        question: "だれが困ってる？",
        answer: "54店舗の発注担当",
        plain: "つまり、毎朝「牛乳を何本頼むか」を決めている人。",
      },
      {
        question: "この課題は？",
        answer: "2週間先までの日々の個数",
        plain: "つまり、届くまでに時間がかかるので、今日のうちに棚の埋まり方を決める。",
      },
      {
        question: "当たると？",
        answer: "品切れと廃棄が減る",
        plain: "つまり、少なすぎると売り逃し、多すぎると生鮮を捨てる。",
      },
    ],
    math: {
      left: "54店",
      middle: "33売り場",
      right: "16日",
      total: "28,512",
      unit: "毎回これだけ決める",
    },
    jargon: [
      { term: "商品ファミリー", plain: "つまり売り場のくくり（パン、精肉、日用品…）" },
      { term: "系列", plain: "つまり「◯◯店の精肉」1本。全部で1,782本" },
      { term: "オンプロモーション", plain: "つまり特売に出ている品目数" },
      { term: "ホライズン", plain: "つまり何日先か。遠いほど当てにくい" },
      { term: "RMSLE", plain: "つまり「何倍ずれたか」の平均点。低いほど良い" },
      { term: "ホールドアウト", plain: "つまり答えを隠した模擬試験" },
      { term: "ブレンド", plain: "つまり複数の予測の多数決" },
    ],
    scoreBars: [
      { label: "先週と同じ", score: 0.617, kind: "other" },
      { label: "機械学習1本", score: 0.4365, kind: "other" },
      { label: "最初の提出", score: 0.39515, kind: "other" },
      { label: "いまの候補", score: 0.37657, kind: "ours" },
    ],
    scoreLead: "低いほど良い。0.62≈1.9倍ずれ、0.38≈1.46倍。",
    struggles: [
      {
        family: "LINGERIE",
        familiar: "下着売り場",
        score: 0.613,
        plain: "売れない日が多く、ゼロと勘違いしやすい",
      },
      {
        family: "GROCERY II",
        familiar: "小さめの食料品",
        score: 0.568,
        plain: "急に売れ方が変わり、多めに見てしまいがち",
      },
      {
        family: "CELEBRATION",
        familiar: "パーティー用品",
        score: 0.533,
        plain: "イベントのときだけ跳ねる",
      },
      {
        family: "HARDWARE",
        familiar: "金物・工具",
        score: 0.521,
        plain: "普段は静かで、たまにまとめて売れる",
      },
      {
        family: "AUTOMOTIVE",
        familiar: "車用品",
        score: 0.501,
        plain: "買う人が限られ、日によって0が続く",
      },
    ],
  },
  pillars: [
    {
      title: "誰が困っているか",
      lead: "各店舗の発注担当",
      body: "54店舗 × 33商品ファミリーで、毎日 1,782 通りの発注量を決めている。",
    },
    {
      title: "何を解くか",
      lead: "16日先までの日次売上",
      body: "発注してから棚に並ぶまでの時間があるので、今日の判断には2週間先が必要。",
    },
    {
      title: "当たると何が変わるか",
      lead: "欠品と廃棄が同時に減る",
      body: "少なく見れば売り逃し、多く見れば廃棄。予測を締めれば両方減る。",
    },
    {
      title: "影響の大きさ",
      lead: "毎日 28,512 個の判断",
      body: "1,782系列 × 16日分が、そのまま発注量になる。",
    },
  ],
  scale: [
    { label: "店舗", value: "54", note: "エクアドル各地" },
    { label: "商品ファミリー", value: "33", note: "食品から日用品まで" },
    { label: "予測する系列", value: "1,782", note: "54 × 33" },
    { label: "学習行数", value: "3,000,888", note: "2013-01-01 〜 2017-08-15" },
    { label: "予測する行数", value: "28,512", note: "2017-08-16 〜 08-31 の16日" },
    { label: "指標", value: "RMSLE", note: "低いほど良い" },
  ],
  metric: {
    name: "RMSLE",
    formulaPlain: "売上を log(1 + 売上) に直してから、ふつうの誤差（二乗平均平方根）を測る。",
    reasons: [
      {
        title: "困り方は「金額」ではなく「割合」",
        body: "3000個を3300と外すのは1割増し。3個を6個と外すのは2倍。店が困るのは後者。",
      },
      {
        title: "大きい店だけを見に行かない",
        body: "そのまま測ると大型店の主力で点が決まる。log なら 1,782 系列を対等に扱える。",
      },
      {
        title: "売上0の日を扱える",
        body: "log(0) は計算できないが、1 を足せば 0 も扱える。",
      },
      {
        title: "大外しを1回でも嫌う",
        body: "二乗して平均するので、小さな外し何回より大外し1回を重く罰する。",
      },
    ],
    example: {
      caption: "同じ「外し方」を2つの指標で比べる",
      rows: [
        {
          case: "主力を1割多め",
          actual: "3,000",
          pred: "3,300",
          rawError: "300（大きい）",
          metricError: "0.095（小さい）",
        },
        {
          case: "少量を2倍に見た",
          actual: "3",
          pred: "6",
          rawError: "3（小さい）",
          metricError: "0.560（大きい）",
        },
      ],
      note: "ふつうの誤差だと上が重いが、店にとって深刻なのは下。",
    },
    limits: "金額損失とは一致しない。ここでは順位を競う物差しとして使う。",
  },
  difficulty: [
    {
      title: "大きい商品と小さい商品が混ざる",
      body: "GROCERY I は1日数千、BOOKS はほぼ0。だから指標が log（RMSLE）。",
    },
    {
      title: "週・給料日・祝日の3つの波",
      body: "曜日で動き、15日と月末に跳ね、祝日で形が変わる。",
    },
    {
      title: "国の事情が売上に出る",
      body: "原油価格が消費に効く。2016年の地震の週はふだんの法則が崩れる。",
    },
    {
      title: "売っていない組み合わせがある",
      body: "扱いを止めた商品は0が続く。ここを0と言い切れるかで順位が変わる。",
    },
  ],
  scoreGuide: [
    { score: "0.90", label: "去年の同じ日の平均", factor: "約2.5倍" },
    { score: "0.61", label: "直近の移動平均", factor: "約1.8倍" },
    { score: "0.43", label: "素直な勾配ブースティング", factor: "約1.5倍" },
    { score: "0.40", label: "ラグとカレンダーを整えた版", factor: "約1.5倍" },
    { score: "0.38", label: "いまの提出候補帯", factor: "約1.46倍" },
    { score: "0.37", label: "公開LBの上位帯", factor: "約1.45倍" },
  ],
  scoreNote: "上位帯は狭いので、効く工夫を1つずつ積む。",
  approach: [
    {
      title: "log で学ぶ",
      body: "指標が log なので、モデルも log(1+売上) を当てて最後に戻す。",
    },
    {
      title: "16日以上前の実績だけ使う",
      body: "本番では直近の売上は手に入らない。使えるふりをすると検証だけ当たる。",
    },
    {
      title: "同じ窓で比べる",
      body: "複数の作り方を、学習末尾16日で採点する。",
    },
    {
      title: "混ぜ方も検証で決める",
      body: "人が勘で重みを決めない。見ていない店舗でも効く混ぜ方だけ残す。",
    },
  ],
  submissions: [
    {
      date: "2026-09-16",
      leaderboard: 0.39515,
      localRmsle: 0.4,
      method: "Chronos-2 74% + LightGBM 26%（最初の提出）",
    },
  ],
  nextSteps: [
    "下着売り場（LINGERIE）と小さめ食料品（GROCERY II）を正直採点で改善する。",
    "公開LBでいまの提出候補 0.37680 が再現するか確認する。",
  ],
  demoNote: "デモは公式と同じ列名の縮小データ（4店舗 × 6ファミリー）です。",
};

export default storeSales;
