"use client";

import { Bar, BarChart, Cell, LabelList, ResponsiveContainer, XAxis, YAxis } from "recharts";
import { Overview } from "@/components/overview";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import type { CompetitionContent } from "@/lib/competitions";
import {
  STORE_SALES_EXPERIMENTS,
  comparableScore,
  experimentsByScore,
  submitRecommendation,
  type ExperimentInsight,
} from "@/lib/competitions/store-sales-experiments";

/**
 * 読み物だけの版。手元のPythonにも outputs/ にも触らないので、
 * GitHub Pages のような静的な置き場でもそのまま開ける。スマホ幅を先に考える。
 */
export function Report({ content }: { content: CompetitionContent }) {
  const rec = submitRecommendation();
  const ranked = experimentsByScore();
  const improvements = STORE_SALES_EXPERIMENTS.filter(
    (item) => item.outcome === "改善" || item.submitAction === "already_submitted"
  );
  const rejected = STORE_SALES_EXPERIMENTS.filter((item) => item.outcome === "不採用");
  const submitted = STORE_SALES_EXPERIMENTS.find((item) => item.leaderboard != null);

  const bars = ranked.slice(0, 10).map((item) => ({
    name: item.title,
    score: comparableScore(item),
    best: item.id === rec.experiment.id,
  }));

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-col gap-8 px-4 py-8">
      <Alert>
        <AlertTitle className="leading-snug">{rec.headline}</AlertTitle>
        <AlertDescription className="leading-relaxed">
          <span className="font-medium text-foreground">つまり：</span>
          {rec.experiment.plain}
        </AlertDescription>
      </Alert>

      <Overview content={content} />

      <Separator />

      <section className="flex flex-col gap-3">
        <div>
          <h2 className="font-heading text-xl tracking-tight">点数の並び</h2>
          <p className="text-sm text-muted-foreground">
            短いほど良い。青が次に出す版。点数は「混ぜ方を決めていない店」で採点。
          </p>
        </div>
        <Card>
          <CardContent className="h-80 pt-4">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={bars}
                layout="vertical"
                margin={{ left: 4, right: 52, top: 0, bottom: 0 }}
              >
                <XAxis type="number" domain={[0.35, 0.65]} hide />
                <YAxis type="category" dataKey="name" width={120} tick={{ fontSize: 10 }} />
                <Bar dataKey="score" radius={[0, 3, 3, 0]} barSize={14}>
                  {bars.map((bar) => (
                    <Cell key={bar.name} fill={bar.best ? "#2563eb" : "#a1a1aa"} />
                  ))}
                  <LabelList
                    dataKey="score"
                    position="right"
                    className="fill-foreground font-mono"
                    fontSize={10}
                    formatter={(value) => Number(value).toFixed(5)}
                  />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </section>

      <section className="flex flex-col gap-3">
        <div>
          <h2 className="font-heading text-xl tracking-tight">良くなった順に</h2>
          <p className="text-sm text-muted-foreground">
            採用した版だけを、上から古い順に並べています。
          </p>
        </div>
        {improvements.map((item) => (
          <Entry key={item.id} item={item} />
        ))}
      </section>

      <section className="flex flex-col gap-3">
        <div>
          <h2 className="font-heading text-xl tracking-tight">
            うまくいかなかった試行（{rejected.length}件）
          </h2>
          <p className="text-sm text-muted-foreground">
            消さずに残します。なぜ外したかが、次に何を試すかを決めます。
          </p>
        </div>
        {rejected.map((item) => (
          <Entry key={item.id} item={item} />
        ))}
      </section>

      <footer className="flex flex-col gap-2 pb-8 text-xs text-muted-foreground">
        <p>
          {submitted?.leaderboard
            ? `公開リーダーボードが分かっているのは最初の提出だけで、${submitted.leaderboard.toFixed(5)} でした。`
            : "公開リーダーボードの記録はまだありません。"}
        </p>
        <p>
          この版は読み物だけです。予測の実行・Championの戻し・Kaggleへの提出は、手元で
          <code className="mx-1 rounded bg-muted px-1 py-0.5">npm run dev</code>
          を動かしたときだけ使えます。
        </p>
      </footer>
    </main>
  );
}

function Entry({ item }: { item: ExperimentInsight }) {
  const failed = item.outcome === "不採用";
  return (
    <Card size="sm" className={item.submitAction === "submit_now" ? "border-primary/40" : undefined}>
      <CardHeader className="gap-1.5 pb-2">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={failed ? "outline" : item.leaderboard != null ? "secondary" : "default"}>
            {failed ? "不採用" : item.leaderboard != null ? "提出済み" : "採用"}
          </Badge>
          <span className="font-mono text-sm">{comparableScore(item).toFixed(5)}</span>
          {item.leaderboard != null ? (
            <span className="font-mono text-xs text-orange-600">
              本番 {item.leaderboard.toFixed(5)}
            </span>
          ) : null}
        </div>
        <CardTitle className="text-base leading-snug">{item.title}</CardTitle>
        <CardDescription className="leading-relaxed">{item.plain}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-1.5 text-sm text-muted-foreground">
        <p>
          <span className="font-medium text-foreground">結果：</span>
          {item.result}
        </p>
        <p>
          <span className="font-medium text-foreground">学び：</span>
          {item.learned}
        </p>
      </CardContent>
    </Card>
  );
}
