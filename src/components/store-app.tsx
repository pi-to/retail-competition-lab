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
import { KaggleData } from "@/components/kaggle-data";
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
import type { KaggleStatus, Result, ResultPayload, RunError, Status } from "@/lib/types";

export function StoreApp({
  content,
  initialResult,
  initialStatus,
  initialError,
  initialRunning,
  kaggleStatus,
}: {
  content: CompetitionContent;
  initialResult: Result | null;
  initialStatus: Status | null;
  initialError: RunError | null;
  initialRunning: boolean;
  kaggleStatus: KaggleStatus;
}) {
  const [result, setResult] = useState<Result | null>(initialResult);
  const [status, setStatus] = useState<Status | null>(initialStatus);
  const [error, setError] = useState<RunError | null>(initialError);
  const [running, setRunning] = useState(initialRunning);
  const [source, setSource] = useState<"demo" | "kaggle">(
    initialResult?.source === "kaggle" ? "kaggle" : "demo"
  );

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
        body: JSON.stringify({ source, competition: content.slug }),
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
    <div className="flex flex-col gap-10">
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
        <SectionTitle title="動かす" sub="手元で実際に採点してみる" />
        <KaggleData initialStatus={kaggleStatus} onReady={() => setSource("kaggle")} />
        <Card>
          <CardHeader>
            <CardDescription>
              {content.demoNote}公式データを取ると、そのまま提出できる submission.csv が{" "}
              <code>outputs/{content.slug}/</code> に出ます。
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <div className="flex flex-wrap items-center gap-2">
              <Button
                variant={source === "demo" ? "default" : "outline"}
                onClick={() => setSource("demo")}
                disabled={running}
              >
                デモデータ
              </Button>
              <Button
                variant={source === "kaggle" ? "default" : "outline"}
                onClick={() => setSource("kaggle")}
                disabled={running}
              >
                公式Kaggle CSV
              </Button>
              <Button onClick={() => void start()} disabled={running}>
                {running ? "実行中…" : "予測を実行"}
              </Button>
              <Button variant="outline" asChild>
                <a href="/api/submission">submission.csv</a>
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
                <p className="text-xs text-muted-foreground">
                  別プロセスで走っています。このページを閉じても実験は続き、
                  戻ってくれば途中から進捗が見えます。
                </p>
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
          <section className="flex flex-col gap-3">
            <SectionTitle
              title="検証レポート"
              sub={`${result.source === "kaggle" ? "公式データ" : "デモデータ"}・どのデータをどれだけ使い、どう当たったか`}
            />
            <ClientReport result={result} />
          </section>

          <section className="flex flex-col gap-3">
            <SectionTitle title="採点の詳細" sub="コンペの指標と混合の重み" />
            <div className="grid gap-3 sm:grid-cols-3">
              <Stat label="混合の検証 RMSLE" value={blend?.rmsle?.toFixed(4) ?? "—"} />
              <Stat label="系列数" value={String(result.n_series)} />
              <Stat label="所要時間" value={`${result.elapsed_sec}s`} />
            </div>
            <Card>
              <CardContent>
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>モデル</TableHead>
                        <TableHead>出自</TableHead>
                        <TableHead className="text-right">RMSLE</TableHead>
                        <TableHead className="text-right">重み</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {result.models.map((m) => (
                        <TableRow key={m.id}>
                          <TableCell className="min-w-56">
                            <div className="font-medium">{m.title}</div>
                            <div className="text-xs text-muted-foreground">{m.note}</div>
                            {m.error ? (
                              <div className="text-xs text-destructive">{m.error}</div>
                            ) : null}
                          </TableCell>
                          <TableCell>{m.org ?? (m.id === "blend" ? "混合" : "古典")}</TableCell>
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
                {best ? (
                  <p className="mt-3 text-sm text-muted-foreground">
                    単体の一位は {best.title}（{best.rmsle?.toFixed(4)}）。混合が単体一位より悪いときは、弱いモデルを混ぜ過ぎている合図なので重みを見直す。
                  </p>
                ) : null}
              </CardContent>
            </Card>
          </section>

          <section className="flex flex-col gap-3">
            <SectionTitle
              title="当たり方を目で見る"
              sub={`一番売れている系列（${result.preview.series_id}）の検証窓`}
            />
            <Card>
              <CardContent className="h-72">
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
                    <Line type="monotone" dataKey="blend" stroke="#7c3aed" dot={false} strokeDasharray="4 4" />
                  </LineChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </section>

          <section className="grid gap-3 md:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>LightGBM が実際に見ていた列</CardTitle>
                <CardDescription>木の分割に使われた回数。上ほど効いている。</CardDescription>
              </CardHeader>
              <CardContent>
                <ul className="space-y-2">
                  {result.feature_importance.slice(0, 10).map((f) => (
                    <li key={f.feature} className="flex items-center justify-between gap-3 text-sm">
                      <span className="font-mono">{f.feature}</span>
                      <span className="text-muted-foreground">{f.gain}</span>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>上位を狙うなら次に足すこと</CardTitle>
                <CardDescription>公開されている上位解法で効くと分かっている順。</CardDescription>
              </CardHeader>
              <CardContent className="space-y-2 text-sm text-muted-foreground">
                {content.nextSteps.map((step, i) => (
                  <p key={step}>
                    {i + 1}. {step}
                  </p>
                ))}
              </CardContent>
            </Card>
          </section>
        </>
      ) : (
        <Alert>
          <AlertTitle>まだ結果がありません</AlertTitle>
          <AlertDescription>
            「予測を実行」で採点します。初回は Chronos-2 と TimesFM の重みを取得するため数分かかることがあります。
          </AlertDescription>
        </Alert>
      )}
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
