"use client";

import { useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  STORE_SALES_EXPERIMENTS,
  SUBMIT_LABEL,
  comparableScore,
  experimentsByScore,
  submitRecommendation,
  type ExperimentInsight,
  type SubmitAction,
} from "@/lib/competitions/store-sales-experiments";

type Run = {
  run_id: string;
  label: string;
  created_at: string;
  local_rmsle: number;
  holdout_rmsle?: number | null;
  leaderboard: number | null;
  method_version: string;
};

export type RunHistory = { runs: Run[]; tags: Record<string, string> };

const ACTION_VARIANT: Record<SubmitAction, "default" | "secondary" | "outline" | "destructive"> = {
  submit_now: "default",
  already_submitted: "secondary",
  do_not_submit: "outline",
  superseded: "outline",
};

export function ExperimentHistory({
  competition,
  initial,
}: {
  competition: string;
  initial: RunHistory;
}) {
  const rec = submitRecommendation();
  const ranked = experimentsByScore();
  const improved = STORE_SALES_EXPERIMENTS.filter((item) => item.outcome !== "不採用");
  const failed = STORE_SALES_EXPERIMENTS.filter((item) => item.outcome === "不採用");
  const [selected, setSelected] = useState<string>(rec.experiment.id);
  const [showFailed, setShowFailed] = useState(false);
  const [history, setHistory] = useState(initial);
  const [pending, setPending] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const insight = ranked.find((item) => item.id === selected) ?? rec.experiment;
  const visible = showFailed ? ranked : ranked.filter((item) => item.outcome !== "不採用");
  const trail = [...improved]
    .sort((a, b) => comparableScore(b) - comparableScore(a))
    .map((item, index) => ({
      step: index + 1,
      name: item.title,
      score: comparableScore(item),
    }));

  async function refresh() {
    const response = await fetch(`/api/runs?competition=${competition}`, { cache: "no-store" });
    if (response.ok) setHistory((await response.json()) as RunHistory);
  }

  async function promote(runId: string) {
    const response = await fetch("/api/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ competition, action: "promote", ref: runId }),
    });
    if (!response.ok) {
      const data = (await response.json()) as { error?: string };
      setMessage(data.error ?? "戻せませんでした。");
      return;
    }
    setMessage(`${runId} へ戻しました。提出CSVもそのRunのものです。`);
    setPending(null);
    await refresh();
    window.location.reload();
  }

  return (
    <Tabs defaultValue="insights">
      <TabsList>
        <TabsTrigger value="insights">やったこと</TabsTrigger>
        <TabsTrigger value="runs">戻す</TabsTrigger>
        <TabsTrigger value="article">記事草稿</TabsTrigger>
      </TabsList>

      <TabsContent value="insights" className="mt-3 flex flex-col gap-3">
        <Alert>
          <AlertTitle>{rec.headline}</AlertTitle>
          <AlertDescription>{rec.experiment.plain}</AlertDescription>
        </Alert>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">ここまでの縮み方</CardTitle>
            <CardDescription>
              左から右へ、試すたびに点数が下がってきた。下ほど良い。
              橙の破線は、実際にKaggleへ出して確かめた 0.39515。
            </CardDescription>
          </CardHeader>
          <CardContent className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={trail} margin={{ left: 4, right: 12, top: 8, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="step" tick={{ fontSize: 11 }} />
                <YAxis
                  domain={[0.36, 0.42]}
                  tick={{ fontSize: 11 }}
                  tickFormatter={(value) => Number(value).toFixed(2)}
                />
                <Tooltip
                  formatter={(value) => Number(value).toFixed(5)}
                  labelFormatter={(step) =>
                    trail.find((item) => item.step === step)?.name ?? `${step}`
                  }
                />
                <ReferenceLine y={0.39515} stroke="#f97316" strokeDasharray="4 4" />
                <Line
                  type="monotone"
                  dataKey="score"
                  stroke="#2563eb"
                  strokeWidth={2}
                  dot={{ r: 3 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">試したこと</CardTitle>
            <CardDescription>
              点数が良い順。点数は、混ぜ方を決めるのに使っていない店舗で採点したものです。
              行を押すと、なぜそうなったかが下に出ます。
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>提出</TableHead>
                    <TableHead className="text-right">点数</TableHead>
                    <TableHead>やったこと</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {visible.map((item) => (
                    <TableRow
                      key={item.id}
                      data-state={item.id === selected ? "selected" : undefined}
                      className={item.submitAction === "submit_now" ? "bg-primary/5" : undefined}
                      onClick={() => setSelected(item.id)}
                    >
                      <TableCell>
                        {item.submitAction === "do_not_submit" ? (
                          <span className="text-muted-foreground">—</span>
                        ) : (
                          <Badge variant={ACTION_VARIANT[item.submitAction]}>
                            {SUBMIT_LABEL[item.submitAction]}
                          </Badge>
                        )}
                      </TableCell>
                      <TableCell className="text-right font-mono font-medium">
                        {comparableScore(item).toFixed(4)}
                        {item.leaderboard != null ? (
                          <span className="block text-xs font-normal text-muted-foreground">
                            本番 {item.leaderboard.toFixed(4)}
                          </span>
                        ) : null}
                      </TableCell>
                      <TableCell className="max-w-xl whitespace-normal">
                        <span className="font-medium">{item.title}</span>
                        <span className="block text-sm text-muted-foreground">{item.plain}</span>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
            <Button
              variant="outline"
              size="sm"
              className="self-start"
              onClick={() => setShowFailed((value) => !value)}
            >
              {showFailed
                ? "うまくいかなかった試行を隠す"
                : `うまくいかなかった試行も見る（${failed.length}件）`}
            </Button>
          </CardContent>
        </Card>

        <InsightDetail insight={insight} />
      </TabsContent>

      <TabsContent value="runs" className="mt-3 flex flex-col gap-3">
        <Alert>
          <AlertTitle>前の版にいつでも戻せます</AlertTitle>
          <AlertDescription>
            提出用のCSVは、いま選ばれている1本だけ。過去の実験はそのまま残してあるので、
            悪くなったら押すだけで戻せます。
          </AlertDescription>
        </Alert>
        {message ? <p className="text-sm text-muted-foreground">{message}</p> : null}
        <Card>
          <CardContent>
            {history.runs.length === 0 ? (
              <p className="py-4 text-sm text-muted-foreground">
                この環境に保存された実験はありません。判断は上の表を見てください。
              </p>
            ) : (
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>提出CSV</TableHead>
                      <TableHead className="text-right">点数</TableHead>
                      <TableHead>実験</TableHead>
                      <TableHead></TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {history.runs.map((run) => {
                      const tags = Object.entries(history.tags)
                        .filter(([, id]) => id === run.run_id)
                        .map(([tag]) => tag);
                      const isChampion = tags.includes("champion");
                      return (
                        <TableRow
                          key={run.run_id}
                          className={isChampion ? "bg-primary/5" : undefined}
                        >
                          <TableCell>
                            {isChampion ? (
                              <Badge>いまの提出CSV</Badge>
                            ) : (
                              <span className="text-muted-foreground">—</span>
                            )}
                          </TableCell>
                          <TableCell className="text-right font-mono">
                            {(run.holdout_rmsle ?? run.local_rmsle).toFixed(4)}
                            {run.leaderboard !== null ? (
                              <span className="block text-xs text-muted-foreground">
                                本番 {run.leaderboard.toFixed(4)}
                              </span>
                            ) : null}
                          </TableCell>
                          <TableCell className="max-w-64 whitespace-normal">
                            <span>{run.label}</span>
                            <span className="block font-mono text-xs text-muted-foreground">
                              {run.created_at.slice(0, 16).replace("T", " ")}
                            </span>
                          </TableCell>
                          <TableCell>
                            {pending === run.run_id ? (
                              <div className="flex gap-2">
                                <Button size="sm" onClick={() => void promote(run.run_id)}>
                                  これに戻す
                                </Button>
                                <Button size="sm" variant="outline" onClick={() => setPending(null)}>
                                  やめる
                                </Button>
                              </div>
                            ) : (
                              <Button
                                size="sm"
                                variant="outline"
                                disabled={isChampion}
                                onClick={() => setPending(run.run_id)}
                              >
                                戻す
                              </Button>
                            )}
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>
      </TabsContent>

      <TabsContent value="article" className="mt-3">
        <Card>
          <CardHeader>
            <CardTitle>DevelopersIO記事草稿</CardTitle>
            <CardDescription>
              うまくいった話だけでなく、効かなかった試行とその理由仮説も入れています。
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3 text-sm text-muted-foreground">
            <p>
              タイトル案：「時系列基盤モデルを小売需要予測に入れてみた —
              うまくいったこと、いかなかったこと」
            </p>
            <Button asChild>
              <a href="/api/article">Markdown草稿をダウンロード</a>
            </Button>
          </CardContent>
        </Card>
      </TabsContent>
    </Tabs>
  );
}

function InsightDetail({ insight }: { insight: ExperimentInsight }) {
  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2 text-sm">
          {insight.title}
          <Badge variant={ACTION_VARIANT[insight.submitAction]}>
            {SUBMIT_LABEL[insight.submitAction]}
          </Badge>
        </CardTitle>
        <CardDescription>
          模擬試験 {comparableScore(insight).toFixed(5)}
          {insight.holdoutRmsle != null
            ? `（当てはめた行なら ${insight.localRmsle.toFixed(5)}）`
            : ""}
          {insight.leaderboard ? ` / 本番 ${insight.leaderboard.toFixed(5)}` : " / 本番は未提出"}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2 text-sm text-muted-foreground">
        <p>
          <span className="font-medium text-foreground">やったこと：</span>
          {insight.tried}
        </p>
        <p>
          <span className="font-medium text-foreground">結果：</span>
          {insight.result}
        </p>
        <p>
          <span className="font-medium text-foreground">なぜそうなったか：</span>
          {insight.why}
        </p>
        <p>
          <span className="font-medium text-foreground">次への学び：</span>
          {insight.learned}
        </p>
      </CardContent>
    </Card>
  );
}
