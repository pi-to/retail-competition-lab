/** 最初の画面で読ませる分だけ。専門語は残し、「つまり」で言い換える。 */
export type PlainSummary = {
  gist: string;
  cards: { question: string; answer: string; plain: string }[];
  math: { left: string; middle: string; right: string; total: string; unit: string };
  jargon: { term: string; plain: string }[];
  scoreBars: { label: string; score: number; kind: "ours" | "other" }[];
  scoreLead: string;
};

/** 画面が1コンペを説明するために必要な文章と数字。 */
export type CompetitionContent = {
  slug: string;
  title: string;
  headline: string;
  oneLine: string;
  badges: string[];
  plain: PlainSummary;
  pillars: { title: string; lead: string; body: string }[];
  scale: { label: string; value: string; note: string }[];
  metric: {
    name: string;
    formulaPlain: string;
    reasons: { title: string; body: string }[];
    example: {
      caption: string;
      rows: { case: string; actual: string; pred: string; rawError: string; metricError: string }[];
      note: string;
    };
    limits: string;
  };
  difficulty: { title: string; body: string }[];
  scoreGuide: { score: string; label: string; factor: string }[];
  scoreNote: string;
  approach: { title: string; body: string }[];
  submissions: {
    date: string;
    leaderboard: number;
    localRmsle: number;
    method: string;
  }[];
  nextSteps: string[];
  demoNote: string;
};
