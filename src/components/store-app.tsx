"use client";

import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ClientReport } from "@/components/client-report";
import { ExperimentHistory, type RunHistory } from "@/components/experiment-history";
import { SubmitCard } from "@/components/submit-card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
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
import type { Result, ResultPayload, RunError, Status } from "@/lib/types";

const STRATEGY_LABEL: Record<string, string> = {
  rule: "逆RMSLE重み",
  fitted: "検証で当てた重み",
  fitted_horizon: "予測日ごとの重み",
  fitted_family: "商品ファミリーごとの重み",
  single: "単体そのまま",
};

export function StoreApp({
  content,
  initialResult,
  initialStatus,
  initialError,
  initialRunning,
  runHistory,
}: {
  content: CompetitionContent;
  initialResult: Result | null;
  initialStatus: Status | null;
  initialError: RunError | null;
  initialRunning: boolean;
  runHistory: RunHistory;
}) {
  const [result, setResult] = useState<Result | null>(initialResult);
  const [status, setStatus] = useState<Status | null>(initialStatus);
  const [error, setError] = useState<RunError | null>(initialError);
  const [running, setRunning] = useState(initialRunning);

  /** 実験は別プロセスで走る。画面はファイルに書かれた進捗を読むだけ。 */
  useEffect(() => {
    if (!running) return;
    const id = setInterval(async () => {
      const res = await fetch(`/api/result?competition=${content.slug}`, { cache: "no-store" });
      if (!res.ok) return;
      const data = (await res.json()) as ResultPayload;
      setResult(data.result);
      setStatus(data.status);
      setError(data.error);
      setRunning(data.running);
    }, 2000);
    return () => clearInterval(id);
  }, [running, content.slug]);

  async function start() {
    setError(null);
    setRunning(true);
    try {
      const res = await fetch("/api/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source: "kaggle", competition: content.slug }),
      });
      if (!res.ok) {
        const data = (await res.json().catch(() => ({}))) as { error?: string };
        setError({ message: data.error ?? "実行を開始できませんでした" });
        setRunning(false);
      }
    } catch (err) {
      setError({ message: err instanceof Error ? err.message : "実行を開始できませんでした" });
      setRunning(false);
    }
  }

  const chartData = useMemo(() => {
    if (!result) return [];
    const map = new Map<string, Record<string, string | number>>();
    for (const p of result.preview.history) {
      map.set(p.date, { date: p.date.slice(5), actual: p.sales ?? 0 });
    }
    for (const p of result.preview.actual) {
      const row = map.get(p.date) ?? { date: p.date.slice(5) };
      row.actual = p.sales ?? 0;
      map.set(p.date, row);
    }
    for (const [name, pts] of Object.entries(result.preview.models)) {
      for (const p of pts) {
        const row = map.get(p.date) ?? { date: p.date.slice(5) };
        row[name] = p.pred ?? 0;
        map.set(p.date, row);
      }
    }
    return [...map.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([, v]) => v);
  }, [result]);

  const blend = result?.models.find((m) => m.id === "blend");
  const best = result?.models
    .filter((m) => m.id !== "blend" && m.status === "ok")
    .slice()
    .sort((a, b) => (a.rmsle ?? 9) - (b.rmsle ?? 9))[0];

  return (
    <div className="flex flex-col gap-8">
      <section className="flex flex-col gap-3">
        <SectionTitle
          title="実験の履歴"
          sub="試したことと点数の縮み方。くわしい理屈は行を押して一言だけ。"
        />
        <ExperimentHistory competition={content.slug} initial={runHistory} />
      </section>

      {result ? (
        <section className="flex flex-col gap-3">
          <SectionTitle title="提出" sub="迷ったら『次に提出する』1本だけ。" />
          <SubmitCard result={result} />
        </section>
      ) : (
        <Alert>
          <AlertTitle>まだ結果がありません</AlertTitle>
          <AlertDescription>
            下の再計算で公式データを採点すると、提出ボタンが使えるようになります。
          </AlertDescription>
        </Alert>
      )}

      <details className="rounded-lg border px-4 py-3">
        <summary className="cursor-pointer text-sm font-medium">再計算・解き方・くわしい数字</summary>
        <div className="mt-4 flex flex-col gap-6">
          <section className="flex flex-col gap-3">
            <SectionTitle title="解き方" sub="覚えることは4つだけ" />
            <div className="grid gap-3 sm:grid-cols-2">
              {content.approach.map((step, i) => (
                <Card key={step.title} size="sm">
                  <CardHeader>
                    <CardTitle className="text-sm">
                      <span className="mr-2 font-mono text-muted-foreground">{i + 1}</span>
                      {step.title}
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="text-sm text-muted-foreground">{step.body}</CardContent>
                </Card>
              ))}
            </div>
          </section>

          <section className="flex flex-col gap-3">
            <SectionTitle title="再計算" sub="公式データで全モデルをもう一度動かす" />
            <Card>
              <CardHeader>
                <CardDescription>
                  1,782系列を検証し、提出ファイルを更新します。通常は6〜7分。
                </CardDescription>
              </CardHeader>
              <CardContent className="flex flex-col gap-4">
                <div className="flex flex-wrap items-center gap-2">
                  <Button onClick={() => void start()} disabled={running}>
                    {running ? "再計算中…" : "公式データで再計算"}
                  </Button>
                  <Button variant="outline" asChild>
                    <a href={`/api/submission?competition=${content.slug}`}>CSVを確認</a>
                  </Button>
                </div>
                {running ? (
                  <div className="flex flex-col gap-2">
                    <p className="text-sm text-muted-foreground">
                      {status ? `${status.pct}% ${status.message}` : "起動しています"}
                    </p>
                    <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
                      <div
                        className="h-full bg-primary transition-all"
                        style={{ width: `${status?.pct ?? 1}%` }}
                      />
                    </div>
                  </div>
                ) : null}
                {error ? (
                  <Alert variant="destructive">
                    <AlertTitle>失敗</AlertTitle>
                    <AlertDescription className="whitespace-pre-wrap">
                      {error.message}
                      {error.hint ? `\n${error.hint}` : ""}
                    </AlertDescription>
                  </Alert>
                ) : null}
              </CardContent>
            </Card>
          </section>

          {result ? (
            <>
              {content.submissions.length > 0 ? (
                <Card size="sm">
                  <CardHeader>
                    <CardTitle className="text-sm">提出の記録</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="overflow-x-auto">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>日付</TableHead>
                            <TableHead className="text-right">公開LB</TableHead>
                            <TableHead className="text-right">ローカル</TableHead>
                            <TableHead>作り方</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {content.submissions.map((entry) => (
                            <TableRow key={entry.date}>
                              <TableCell className="font-mono">{entry.date}</TableCell>
                              <TableCell className="text-right font-mono font-medium">
                                {entry.leaderboard.toFixed(5)}
                              </TableCell>
                              <TableCell className="text-right font-mono text-muted-foreground">
                                {entry.localRmsle.toFixed(4)}
                              </TableCell>
                              <TableCell className="text-muted-foreground">{entry.method}</TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </div>
                  </CardContent>
                </Card>
              ) : null}

              <ClientReport result={result} />

              <div className="grid gap-3 sm:grid-cols-3">
                <Stat label="混合の検証 RMSLE" value={blend?.rmsle?.toFixed(4) ?? "—"} />
                <Stat label="系列数" value={String(result.n_series)} />
                <Stat label="所要時間" value={`${result.elapsed_sec}s`} />
              </div>

              <Card>
                <CardHeader>
                  <CardTitle className="text-sm">モデル別の点数と重み</CardTitle>
                  {best ? (
                    <CardDescription>
                      単体一位は {best.title}（{best.rmsle?.toFixed(4)}）。
                      {blend?.candidates
                        ? `混ぜ方は ${STRATEGY_LABEL[blend.strategy ?? ""] ?? blend.strategy}。`
                        : null}
                    </CardDescription>
                  ) : null}
                </CardHeader>
                <CardContent>
                  <div className="overflow-x-auto">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>モデル</TableHead>
                          <TableHead className="text-right">RMSLE</TableHead>
                          <TableHead className="text-right">重み</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {result.models.map((m) => (
                          <TableRow key={m.id}>
                            <TableCell>
                              <div className="font-medium">{m.title}</div>
                              <div className="text-xs text-muted-foreground">{m.note}</div>
                            </TableCell>
                            <TableCell className="text-right font-mono">
                              {m.rmsle?.toFixed(4) ?? m.status}
                            </TableCell>
                            <TableCell className="text-right font-mono">
                              {m.id === "blend" ? "—" : (m.weight ?? 0).toFixed(3)}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="text-sm">当たり方を目で見る</CardTitle>
                  <CardDescription>
                    一番売れている系列（{result.preview.series_id}）
                  </CardDescription>
                </CardHeader>
                <CardContent className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={chartData}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                      <YAxis tick={{ fontSize: 11 }} />
                      <Tooltip />
                      <Legend />
                      <Line type="monotone" dataKey="actual" stroke="#111" dot={false} strokeWidth={2} />
                      <Line type="monotone" dataKey="lightgbm" stroke="#2563eb" dot={false} />
                      <Line type="monotone" dataKey="chronos2" stroke="#c2410c" dot={false} />
                      <Line type="monotone" dataKey="timesfm" stroke="#15803d" dot={false} />
                      <Line
                        type="monotone"
                        dataKey="blend"
                        stroke="#7c3aed"
                        dot={false}
                        strokeDasharray="4 4"
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>

              <div className="grid gap-3 md:grid-cols-2">
                <Card>
                  <CardHeader>
                    <CardTitle className="text-sm">効いていた列</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <ul className="space-y-1.5">
                      {result.feature_importance.slice(0, 8).map((f) => (
                        <li
                          key={f.feature}
                          className="flex items-center justify-between gap-3 text-sm"
                        >
                          <span className="font-mono text-xs">{f.feature}</span>
                          <span className="text-muted-foreground">{f.gain}</span>
                        </li>
                      ))}
                    </ul>
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader>
                    <CardTitle className="text-sm">次にやること</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2 text-sm text-muted-foreground">
                    {content.nextSteps.map((step, i) => (
                      <p key={step}>
                        {i + 1}. {step}
                      </p>
                    ))}
                  </CardContent>
                </Card>
              </div>
            </>
          ) : null}
        </div>
      </details>
    </div>
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

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <Card size="sm">
      <CardHeader>
        <CardDescription>{label}</CardDescription>
        <CardTitle className="font-mono text-2xl">{value}</CardTitle>
      </CardHeader>
    </Card>
  );
}
