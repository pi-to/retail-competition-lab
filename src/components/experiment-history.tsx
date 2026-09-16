"use client";

import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
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

/** 年表用の短い名前。グラフが読みやすくなる。 */
const SHORT: Record<string, string> = {
  "seasonal-naive": "先週と同じ",
  "direct-lightgbm": "表の機械学習",
  "timesfm-only": "TimesFM単体",
  "chronos-full-context": "Chronos長い文脈",
  "inverse-score-blend": "逆数で混ぜる",
  "zero-21": "21日ゼロ強制",
  "recursive-lgbm-v1": "売り場別の積み上げ",
  "recursive-trees-320": "木を増やす",
  "direct-horizon-lgbm": "日数別一括",
  "recursive320-direct-horizon-v1": "積み上げ+一括",
  "exog-holiday-promo-v1": "祝日・特売",
  "exog-no-eq-v1": "地震を外す",
  "horizon-family-blend-v1": "売り場別の混ぜ方",
  "sparse-recursive-v1": "売れない棚向け",
  "robust-min-family-v1": "控えめに抑える",
  "honest-selection-v1": "採点を正直に",
  "honest-subset-blend-v1": "顔ぶれを絞る",
  "intermittent-recursive-v1": "売れない間隔を教える",
  "foundation-blend-v1": "最初の提出",
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
  const failed = STORE_SALES_EXPERIMENTS.filter((item) => item.outcome === "不採用");
  const [selected, setSelected] = useState<string>(rec.experiment.id);
  const [showFailed, setShowFailed] = useState(true);
  const [history, setHistory] = useState(initial);
  const [pending, setPending] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const insight = ranked.find((item) => item.id === selected) ?? rec.experiment;
  const visible = showFailed ? ranked : ranked.filter((item) => item.outcome !== "不採用");

  /** 時系列の縮み方。点数が良い順ではなく、実験の流れで並べる。 */
  const story = [...STORE_SALES_EXPERIMENTS]
    .filter((item) => item.outcome !== "不採用" || item.leaderboard != null)
    .map((item, index) => ({
      step: index + 1,
      id: item.id,
      name: SHORT[item.id] ?? item.title,
      score: comparableScore(item),
      lb: item.leaderboard ?? null,
      action: item.submitAction,
    }));

  const barRows = visible.map((item) => ({
    id: item.id,
    name: SHORT[item.id] ?? item.title,
    score: comparableScore(item),
    kind:
      item.submitAction === "submit_now"
        ? "ours"
        : item.submitAction === "already_submitted"
          ? "lb"
          : item.outcome === "不採用"
            ? "fail"
            : "other",
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

        <div className="grid gap-3 lg:grid-cols-2">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">ここまでの縮み方</CardTitle>
              <CardDescription>
                左→右で試行が進む。下ほど良い。橙の破線は本番で確かめた 0.395。
              </CardDescription>
            </CardHeader>
            <CardContent className="h-52">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={story} margin={{ left: 0, right: 8, top: 8, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="step" tick={{ fontSize: 10 }} />
                  <YAxis
                    domain={[0.36, 0.42]}
                    tick={{ fontSize: 10 }}
                    width={36}
                    tickFormatter={(value) => Number(value).toFixed(2)}
                  />
                  <Tooltip
                    formatter={(value) => Number(value).toFixed(5)}
                    labelFormatter={(step) =>
                      story.find((item) => item.step === step)?.name ?? `${step}`
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
            <CardHeader className="pb-2">
              <CardTitle className="text-base">点数の並び</CardTitle>
              <CardDescription>短いほど良い。青＝次に出す / 橙＝本番済み。</CardDescription>
            </CardHeader>
            <CardContent className="h-52">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={barRows.slice(0, 10)}
                  layout="vertical"
                  margin={{ left: 4, right: 36, top: 0, bottom: 0 }}
                >
                  <XAxis type="number" domain={[0.35, 0.65]} hide />
                  <YAxis type="category" dataKey="name" width={108} tick={{ fontSize: 10 }} />
                  <Tooltip formatter={(value) => Number(value).toFixed(4)} />
                  <Bar
                    dataKey="score"
                    radius={[0, 3, 3, 0]}
                    barSize={14}
                    onClick={(data) => {
                      const id = (data as { id?: string }).id;
                      if (id) setSelected(id);
                    }}
                  >
                    {barRows.slice(0, 10).map((row) => (
                      <Cell
                        key={row.id}
                        fill={
                          row.kind === "ours"
                            ? "#2563eb"
                            : row.kind === "lb"
                              ? "#ea580c"
                              : row.kind === "fail"
                                ? "#e4e4e7"
                                : "#a1a1aa"
                        }
                        opacity={row.id === selected ? 1 : 0.75}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </div>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">実験の一覧</CardTitle>
            <CardDescription>
              行を押すと下に一言だけ出ます。点数は「混ぜ方を決めていない店」で採点。
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-28">提出</TableHead>
                    <TableHead className="w-20 text-right">点数</TableHead>
                    <TableHead>やったこと</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {visible.map((item) => (
                    <TableRow
                      key={item.id}
                      data-state={item.id === selected ? "selected" : undefined}
                      className={
                        item.submitAction === "submit_now"
                          ? "cursor-pointer bg-primary/5"
                          : "cursor-pointer"
                      }
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
                      <TableCell className="text-right font-mono text-sm font-medium">
                        {comparableScore(item).toFixed(4)}
                        {item.leaderboard != null ? (
                          <span className="block text-[10px] font-normal text-orange-600">
                            本番 {item.leaderboard.toFixed(4)}
                          </span>
                        ) : null}
                      </TableCell>
                      <TableCell className="max-w-xl whitespace-normal py-2">
                        <span className="text-sm font-medium">
                          {SHORT[item.id] ?? item.title}
                        </span>
                        <span className="block text-xs text-muted-foreground">{item.plain}</span>
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
            提出用CSVはいま選ばれている1本だけ。悪くなったら押すだけで戻せます。
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
            <CardDescription>うまくいった話と、いかなかった試行の両方を入れています。</CardDescription>
          </CardHeader>
          <CardContent>
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
      <CardHeader className="pb-2">
        <CardTitle className="flex flex-wrap items-center gap-2 text-sm">
          {SHORT[insight.id] ?? insight.title}
          <Badge variant={ACTION_VARIANT[insight.submitAction]}>
            {SUBMIT_LABEL[insight.submitAction]}
          </Badge>
        </CardTitle>
        <CardDescription>
          模擬試験 {comparableScore(insight).toFixed(5)}
          {insight.leaderboard ? ` / 本番 ${insight.leaderboard.toFixed(5)}` : ""}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-1.5 text-sm text-muted-foreground">
        <p>
          <span className="font-medium text-foreground">つまり：</span>
          {insight.plain}
        </p>
        <p>
          <span className="font-medium text-foreground">結果：</span>
          {insight.result}
        </p>
        <p>
          <span className="font-medium text-foreground">学び：</span>
          {insight.learned}
        </p>
      </CardContent>
    </Card>
  );
}
