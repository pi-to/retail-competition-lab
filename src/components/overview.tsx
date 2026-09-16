"use client";

import { Bar, BarChart, Cell, LabelList, ResponsiveContainer, XAxis, YAxis } from "recharts";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { CompetitionContent } from "@/lib/competitions";

export function Overview({ content }: { content: CompetitionContent }) {
  const { metric, plain } = content;
  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-2">
          {content.badges.map((badge, i) => (
            <Badge key={badge} variant={i === 0 ? "default" : i === 1 ? "secondary" : "outline"}>
              {badge}
            </Badge>
          ))}
        </div>
        <h1 className="font-heading max-w-3xl text-3xl leading-tight tracking-tight sm:text-4xl">
          {content.headline}
        </h1>
        <p className="max-w-3xl text-lg text-muted-foreground">{plain.gist}</p>
      </header>

      <section className="grid gap-3 md:grid-cols-3">
        {plain.cards.map((card) => (
          <Card key={card.question} size="sm">
            <CardHeader>
              <CardDescription>{card.question}</CardDescription>
              <CardTitle className="text-base">{card.answer}</CardTitle>
            </CardHeader>
            <CardContent className="text-sm text-muted-foreground">{card.plain}</CardContent>
          </Card>
        ))}
      </section>

      <section className="grid gap-3 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">予測する数</CardTitle>
            <CardDescription>掛け算するとこの数になる</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <Chip value={plain.math.left} />
              <span className="text-muted-foreground">×</span>
              <Chip value={plain.math.middle} />
              <span className="text-muted-foreground">×</span>
              <Chip value={plain.math.right} />
              <span className="text-muted-foreground">=</span>
              <span className="font-mono text-2xl font-medium">{plain.math.total}</span>
            </div>
            <p className="mt-3 text-sm text-muted-foreground">{plain.math.unit}</p>
            <Horizon />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">いまどれくらい当たるか</CardTitle>
            <CardDescription>{plain.scoreLead}</CardDescription>
          </CardHeader>
          <CardContent className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={plain.scoreBars}
                layout="vertical"
                margin={{ left: 8, right: 46, top: 4, bottom: 4 }}
              >
                <XAxis type="number" domain={[0, 0.7]} hide />
                <YAxis type="category" dataKey="label" width={132} tick={{ fontSize: 11 }} />
                <Bar dataKey="score" radius={[0, 4, 4, 0]}>
                  {plain.scoreBars.map((bar) => (
                    <Cell key={bar.label} fill={bar.kind === "ours" ? "#2563eb" : "#d4d4d8"} />
                  ))}
                  <LabelList
                    dataKey="score"
                    position="right"
                    className="fill-foreground font-mono"
                    fontSize={11}
                  />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </section>

      <section className="flex flex-col gap-3">
        <SectionTitle title="出てくる言葉" sub="専門語はそのまま、意味だけ言い換えます" />
        <Card>
          <CardContent className="grid gap-x-6 gap-y-3 sm:grid-cols-2">
            {plain.jargon.map((item) => (
              <div key={item.term} className="text-sm">
                <span className="font-medium">{item.term}</span>
                <span className="block text-muted-foreground">{item.plain}</span>
              </div>
            ))}
          </CardContent>
        </Card>
      </section>

      <Details summary="なぜこの点数で競うのか（くわしく）">
        <p className="text-sm text-muted-foreground">{metric.formulaPlain}</p>
        <div className="grid gap-3 md:grid-cols-2">
          {metric.reasons.slice(0, 4).map((r) => (
            <Card key={r.title} size="sm">
              <CardHeader>
                <CardTitle className="text-sm">{r.title}</CardTitle>
              </CardHeader>
              <CardContent className="text-sm text-muted-foreground">{r.body}</CardContent>
            </Card>
          ))}
        </div>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">{metric.example.caption}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>状況</TableHead>
                    <TableHead className="text-right">実績</TableHead>
                    <TableHead className="text-right">予測</TableHead>
                    <TableHead className="text-right">ふつうの誤差</TableHead>
                    <TableHead className="text-right">{metric.name} の誤差</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {metric.example.rows.map((r) => (
                    <TableRow key={r.case}>
                      <TableCell className="min-w-36">{r.case}</TableCell>
                      <TableCell className="text-right font-mono">{r.actual}</TableCell>
                      <TableCell className="text-right font-mono">{r.pred}</TableCell>
                      <TableCell className="text-right font-mono">{r.rawError}</TableCell>
                      <TableCell className="text-right font-mono">{r.metricError}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
            <p className="text-sm text-muted-foreground">{metric.example.note}</p>
            <p className="text-sm text-muted-foreground">{metric.limits}</p>
          </CardContent>
        </Card>
      </Details>

      <Details summary="なぜ簡単に当たらないのか（くわしく）">
        <div className="grid gap-3 sm:grid-cols-2">
          {content.difficulty.map((d) => (
            <Card key={d.title} size="sm">
              <CardHeader>
                <CardTitle className="text-sm">{d.title}</CardTitle>
              </CardHeader>
              <CardContent className="text-sm text-muted-foreground">{d.body}</CardContent>
            </Card>
          ))}
        </div>
        <Card>
          <CardContent className="flex flex-col gap-3">
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-20">{metric.name}</TableHead>
                    <TableHead>やり方</TableHead>
                    <TableHead className="text-right">外し方の目安</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {content.scoreGuide.map((s) => (
                    <TableRow key={s.score}>
                      <TableCell className="font-mono">{s.score}</TableCell>
                      <TableCell>{s.label}</TableCell>
                      <TableCell className="text-right text-muted-foreground">{s.factor}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
            <p className="text-sm text-muted-foreground">{content.scoreNote}</p>
          </CardContent>
        </Card>
      </Details>
    </div>
  );
}

function Chip({ value }: { value: string }) {
  return <span className="rounded-md bg-muted px-2 py-1 font-medium">{value}</span>;
}

/** 学習と予測の関係を1本の帯で見せる。数字を読まなくても形が分かるように。 */
function Horizon() {
  return (
    <div className="mt-4 flex flex-col gap-2">
      <div className="flex h-7 overflow-hidden rounded-md text-xs">
        <div className="flex flex-[6] items-center justify-center bg-muted text-muted-foreground">
          これまでの売上（4年半）
        </div>
        <div className="flex flex-[1] items-center justify-center bg-primary/15 text-primary">
          隠して採点する16日
        </div>
        <div className="flex flex-[1] items-center justify-center bg-primary text-primary-foreground">
          提出する16日
        </div>
      </div>
      <p className="text-xs text-muted-foreground">
        真ん中は答えを隠した模擬試験。ここで良かった作り方だけを、右の本番に使います。
      </p>
    </div>
  );
}

function Details({ summary, children }: { summary: string; children: React.ReactNode }) {
  return (
    <details className="group rounded-lg border p-4">
      <summary className="cursor-pointer text-sm font-medium marker:text-muted-foreground">
        {summary}
      </summary>
      <div className="mt-4 flex flex-col gap-3">{children}</div>
    </details>
  );
}

function SectionTitle({ title, sub }: { title: string; sub: string }) {
  return (
    <div className="flex flex-col gap-1">
      <h2 className="font-heading text-xl tracking-tight">{title}</h2>
      <p className="text-sm text-muted-foreground">{sub}</p>
    </div>
  );
}
