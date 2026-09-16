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
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-3">
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
        <p className="max-w-2xl text-base text-muted-foreground">{plain.gist}</p>
      </header>

      <section className="grid gap-3 sm:grid-cols-3">
        {plain.cards.map((card) => (
          <Card key={card.question} size="sm" className="bg-muted/30">
            <CardHeader className="gap-1">
              <CardDescription className="text-xs tracking-wide uppercase">
                {card.question}
              </CardDescription>
              <CardTitle className="text-base leading-snug">{card.answer}</CardTitle>
            </CardHeader>
            <CardContent className="text-sm text-muted-foreground">{card.plain}</CardContent>
          </Card>
        ))}
      </section>

      <section className="grid gap-3 lg:grid-cols-2">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">予測する数</CardTitle>
            <CardDescription>店 × 売り場 × 日数</CardDescription>
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
            <p className="mt-2 text-sm text-muted-foreground">{plain.math.unit}</p>
            <Horizon />
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">いまの点数</CardTitle>
            <CardDescription>{plain.scoreLead}</CardDescription>
          </CardHeader>
          <CardContent className="h-48">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={plain.scoreBars}
                layout="vertical"
                margin={{ left: 4, right: 40, top: 0, bottom: 0 }}
              >
                <XAxis type="number" domain={[0, 0.7]} hide />
                <YAxis type="category" dataKey="label" width={100} tick={{ fontSize: 11 }} />
                <Bar dataKey="score" radius={[0, 4, 4, 0]} barSize={18}>
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

      <section>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">いま一番困っている売り場</CardTitle>
            <CardDescription>
              英語の売り場名はそのまま。右の言い方でイメージしてください。長いほど外しやすい。
            </CardDescription>
          </CardHeader>
          <CardContent className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={plain.struggles}
                layout="vertical"
                margin={{ left: 4, right: 40, top: 4, bottom: 4 }}
              >
                <XAxis type="number" domain={[0, 0.7]} hide />
                <YAxis
                  type="category"
                  dataKey="familiar"
                  width={108}
                  tick={{ fontSize: 11 }}
                />
                <Bar dataKey="score" fill="#ea580c" radius={[0, 4, 4, 0]} barSize={16}>
                  <LabelList
                    dataKey="score"
                    position="right"
                    className="fill-foreground font-mono"
                    fontSize={11}
                  />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
            <ul className="mt-2 grid gap-1 text-xs text-muted-foreground sm:grid-cols-2">
              {plain.struggles.map((item) => (
                <li key={item.family}>
                  <span className="font-medium text-foreground">{item.familiar}</span>
                  <span className="mx-1 font-mono text-[10px]">({item.family})</span>
                  — {item.plain}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </section>

      <section>
        <Card size="sm">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">出てくる言葉</CardTitle>
            <CardDescription>言い換えなくていい。意味だけ添えます。</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            {plain.jargon.map((item) => (
              <span
                key={item.term}
                className="inline-flex max-w-full flex-col rounded-md border bg-background px-2.5 py-1.5 text-xs"
              >
                <span className="font-medium">{item.term}</span>
                <span className="text-muted-foreground">{item.plain}</span>
              </span>
            ))}
          </CardContent>
        </Card>
      </section>

      <Details summary="点数の仕組み（くわしく）">
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
                    <TableHead className="text-right">{metric.name}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {metric.example.rows.map((r) => (
                    <TableRow key={r.case}>
                      <TableCell>{r.case}</TableCell>
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
          </CardContent>
        </Card>
      </Details>

      <Details summary="なぜ簡単に当たらないのか">
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
      </Details>
    </div>
  );
}

function Chip({ value }: { value: string }) {
  return <span className="rounded-md bg-muted px-2 py-1 font-medium">{value}</span>;
}

function Horizon() {
  return (
    <div className="mt-4 flex flex-col gap-1.5">
      <div className="flex h-7 overflow-hidden rounded-md text-[11px]">
        <div className="flex flex-[6] items-center justify-center bg-muted text-muted-foreground">
          これまでの売上
        </div>
        <div className="flex flex-[1] items-center justify-center bg-primary/15 text-primary">
          模擬試験16日
        </div>
        <div className="flex flex-[1] items-center justify-center bg-primary text-primary-foreground">
          提出16日
        </div>
      </div>
      <p className="text-xs text-muted-foreground">
        真ん中で試して良かった作り方だけを、右の本番に使います。
      </p>
    </div>
  );
}

function Details({ summary, children }: { summary: string; children: React.ReactNode }) {
  return (
    <details className="group rounded-lg border px-4 py-3">
      <summary className="cursor-pointer text-sm font-medium marker:text-muted-foreground">
        {summary}
      </summary>
      <div className="mt-3 flex flex-col gap-3">{children}</div>
    </details>
  );
}
