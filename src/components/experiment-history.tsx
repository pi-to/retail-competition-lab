"use client";

import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
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
  leaderboard: number | null;
  method_version: string;
};

export type RunHistory = { runs: Run[]; tags: Record<string, string> };

const COLORS = { 採用: "#2563eb", 改善: "#16a34a", 不採用: "#a1a1aa" };

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
  const [selected, setSelected] = useState<string>(rec.experiment.id);
  const [history, setHistory] = useState(initial);
  const [pending, setPending] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const insight = ranked.find((item) => item.id === selected) ?? rec.experiment;
  const chart = STORE_SALES_EXPERIMENTS.map((item) => ({
    name: short(item.title),
    local: item.localRmsle,
    leaderboard: item.leaderboard,
    outcome: item.outcome,
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
        <TabsTrigger value="insights">試したこと</TabsTrigger>
        <TabsTrigger value="runs">Run履歴・戻す</TabsTrigger>
        <TabsTrigger value="article">記事草稿</TabsTrigger>
      </TabsList>

      <TabsContent value="insights" className="mt-3 flex flex-col gap-3">
        <Alert>
          <AlertTitle>{rec.headline}</AlertTitle>
          <AlertDescription className="flex flex-col gap-1">
            <span>{rec.whyThis}</span>
            <span>{rec.doNotSubmit}</span>
            {rec.experiment.runId ? (
              <span className="font-mono text-xs">Run ID: {rec.experiment.runId}</span>
            ) : null}
          </AlertDescription>
        </Alert>

        <Card>
          <CardHeader>
            <CardTitle>実験履歴</CardTitle>
            <CardDescription>
              ローカルRMSLEが低い順。提出列が空欄に見える行は出さない。行をクリックすると下に理由が出る。
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>提出</TableHead>
                    <TableHead className="text-right">ローカル</TableHead>
                    <TableHead className="text-right">公開LB</TableHead>
                    <TableHead>実験</TableHead>
                    <TableHead>判定</TableHead>
                    <TableHead>タグ</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {ranked.map((item) => {
                    const isSubmit = item.submitAction === "submit_now";
                    return (
                      <TableRow
                        key={item.id}
                        data-state={item.id === selected ? "selected" : undefined}
                        className={isSubmit ? "bg-primary/5" : undefined}
                        onClick={() => setSelected(item.id)}
                      >
                        <TableCell>
                          <Badge variant={ACTION_VARIANT[item.submitAction]}>
                            {SUBMIT_LABEL[item.submitAction]}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right font-mono font-medium">
                          {item.localRmsle.toFixed(5)}
                        </TableCell>
                        <TableCell className="text-right font-mono text-muted-foreground">
                          {item.leaderboard != null ? item.leaderboard.toFixed(5) : "—"}
                        </TableCell>
                        <TableCell className="max-w-56 whitespace-normal font-medium">
                          {item.title}
                        </TableCell>
                        <TableCell>
                          <Badge variant={item.outcome === "不採用" ? "outline" : "secondary"}>
                            {item.outcome}
                          </Badge>
                        </TableCell>
                        <TableCell className="font-mono text-xs text-muted-foreground">
                          {item.tag}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>

        <InsightDetail insight={insight} />

        <Card>
          <CardHeader>
            <CardTitle>試行ごとのローカルRMSLE</CardTitle>
            <CardDescription>低いほど良い。灰色の失敗も消さず、次の判断材料にする。</CardDescription>
          </CardHeader>
          <CardContent className="h-80">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chart} layout="vertical" margin={{ left: 78, right: 20 }}>
                <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                <XAxis type="number" domain={[0.35, 0.65]} tick={{ fontSize: 11 }} />
                <YAxis type="category" dataKey="name" width={125} tick={{ fontSize: 10 }} />
                <Tooltip formatter={(value) => Number(value).toFixed(5)} />
                <Legend />
                <Bar name="ローカル検証" dataKey="local" radius={[0, 4, 4, 0]}>
                  {chart.map((item) => (
                    <Cell key={item.name} fill={COLORS[item.outcome]} />
                  ))}
                </Bar>
                <Bar name="公開LB" dataKey="leaderboard" fill="#f97316" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </TabsContent>

      <TabsContent value="runs" className="mt-3 flex flex-col gap-3">
        <Alert>
          <AlertTitle>タグで安全に戻せます</AlertTitle>
          <AlertDescription>
            Championだけが現在の result.json / submission.csv です。失敗Runも不変のまま残ります。
            「戻す」はコードを変えず、選んだRunの成果物を復元します。Kaggleへ出すのは Champion のCSV。
          </AlertDescription>
        </Alert>
        {message ? <p className="text-sm text-muted-foreground">{message}</p> : null}
        <Card>
          <CardContent>
            {history.runs.length === 0 ? (
              <p className="py-4 text-sm text-muted-foreground">
                この環境にアーカイブされたRunはありません。提出判断は上の実験履歴表を見てください。
              </p>
            ) : (
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>提出CSV</TableHead>
                      <TableHead className="text-right">ローカル</TableHead>
                      <TableHead className="text-right">公開LB</TableHead>
                      <TableHead>ラベル</TableHead>
                      <TableHead>Run ID</TableHead>
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
                            {run.local_rmsle.toFixed(5)}
                          </TableCell>
                          <TableCell className="text-right font-mono text-muted-foreground">
                            {run.leaderboard !== null ? run.leaderboard.toFixed(5) : "—"}
                          </TableCell>
                          <TableCell className="max-w-48 whitespace-normal">
                            <div className="flex flex-wrap items-center gap-1">
                              <span>{run.label}</span>
                              {tags
                                .filter((tag) => tag !== "champion")
                                .map((tag) => (
                                  <Badge key={tag} variant="outline">
                                    {tag}
                                  </Badge>
                                ))}
                            </div>
                          </TableCell>
                          <TableCell className="font-mono text-xs text-muted-foreground">
                            {run.run_id}
                          </TableCell>
                          <TableCell>
                            {pending === run.run_id ? (
                              <div className="flex gap-2">
                                <Button size="sm" onClick={() => void promote(run.run_id)}>
                                  このRunへ戻す
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
                                戻す内容を確認
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
              成功だけでなく、TimesFM・単純混合・固定ゼロ処理が悪化した理由仮説まで書いています。
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
          <Badge variant={insight.outcome === "採用" ? "default" : "outline"}>
            {insight.outcome}
          </Badge>
          <Badge variant="secondary">{insight.tag}</Badge>
        </CardTitle>
        <CardDescription>
          local {insight.localRmsle.toFixed(5)}
          {insight.leaderboard ? ` / LB ${insight.leaderboard.toFixed(5)}` : " / LB 未提出"}
          {insight.runId ? ` / ${insight.runId}` : ""}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2 text-sm text-muted-foreground">
        <p>
          <span className="font-medium text-foreground">試した：</span>
          {insight.tried}
        </p>
        <p>
          <span className="font-medium text-foreground">結果：</span>
          {insight.result}
        </p>
        <p>
          <span className="font-medium text-foreground">原因仮説：</span>
          {insight.why}
        </p>
        <p>
          <span className="font-medium text-foreground">学び：</span>
          {insight.learned}
        </p>
      </CardContent>
    </Card>
  );
}

function short(title: string) {
  return title.length > 15 ? `${title.slice(0, 14)}…` : title;
}
