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
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { Result, Status } from "@/lib/types";

const STATIC_METHOD = [
  {
    title: "何を当てるか",
    body: "Favorita の店×商品ファミリー×日の売上。テストは学習最終日の翌日から16日。指標は RMSLE。",
  },
  {
    title: "なぜ4モデルか",
    body: "ナイーブは下限。LightGBM はプロモと祝日を店横断で学ぶ。Chronos-2 は系列＋未来共変量。TimesFM は AWS に依らない系列モデル。",
  },
  {
    title: "混ぜ方",
    body: "末尾16日を検証に残し、RMSLE の逆数で重み付けする。数字が悪いモデルは自然に薄くなる。",
  },
];

export function StoreApp({
  initialResult,
  initialStatus,
}: {
  initialResult: Result | null;
  initialStatus: Status | null;
}) {
  const [result, setResult] = useState<Result | null>(initialResult);
  const [status, setStatus] = useState<Status | null>(initialStatus);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [source, setSource] = useState<"demo" | "kaggle">("demo");

  async function refresh() {
    const res = await fetch("/api/result", { cache: "no-store" });
    const data = (await res.json()) as { result: Result | null; status: Status | null };
    setResult(data.result);
    setStatus(data.status);
  }

  useEffect(() => {
    if (!running) return;
    const id = setInterval(() => {
      void refresh();
    }, 1500);
    return () => clearInterval(id);
  }, [running]);

  async function start() {
    setRunning(true);
    setError(null);
    try {
      const res = await fetch("/api/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source }),
      });
      const data = (await res.json()) as { ok: boolean; error?: string };
      if (!data.ok) setError(data.error ?? "実行に失敗しました");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "実行に失敗しました");
    } finally {
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
  const ranked = result?.models
    .filter((m) => m.id !== "blend" && m.status === "ok")
    .slice()
    .sort((a, b) => (a.rmsle ?? 9) - (b.rmsle ?? 9));

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-6 px-4 py-8 sm:px-6">
      <header className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <Badge>Kaggle Store Sales</Badge>
          <Badge variant="secondary">RMSLE</Badge>
          <Badge variant="outline">16日先</Badge>
        </div>
        <h1 className="font-heading text-3xl tracking-tight sm:text-4xl">
          売上予測を、後から読める形で解く
        </h1>
        <p className="max-w-2xl text-muted-foreground">
          上位を狙う手順を4つに縮約しています。表モデルと時系列基盤モデル（Amazon Chronos-2 と Google TimesFM）を同じ検証窓で比べ、勝った側を多く混ぜます。
        </p>
      </header>

      <section className="grid gap-3 md:grid-cols-3">
        {STATIC_METHOD.map((step) => (
          <Card key={step.title} size="sm">
            <CardHeader>
              <CardTitle>{step.title}</CardTitle>
            </CardHeader>
            <CardContent className="text-muted-foreground">{step.body}</CardContent>
          </Card>
        ))}
      </section>

      <Card>
        <CardHeader>
          <CardTitle>実験</CardTitle>
          <CardDescription>
            デモは Favorita と同じ列の縮小データです。公式CSVを <code>data/kaggle/</code> に置くと本番と同じ提出ファイルが出ます。
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
          {running || (status && status.step !== "done") ? (
            <p className="text-sm text-muted-foreground">
              {status ? `${status.pct}% ${status.message}` : "起動しています"}
            </p>
          ) : null}
          {error ? (
            <Alert variant="destructive">
              <AlertTitle>失敗</AlertTitle>
              <AlertDescription className="whitespace-pre-wrap">{error}</AlertDescription>
            </Alert>
          ) : null}
        </CardContent>
      </Card>

      {result ? (
        <>
          <section className="grid gap-3 sm:grid-cols-3">
            <Stat label="検証 RMSLE（混合）" value={blend?.rmsle?.toFixed(4) ?? "—"} />
            <Stat label="系列数" value={String(result.n_series)} />
            <Stat label="所要" value={`${result.elapsed_sec}s`} />
          </section>

          <Card>
            <CardHeader>
              <CardTitle>検証スコア</CardTitle>
              <CardDescription>
                学習末尾 {result.horizon} 日。低いほど良い。重みは 1/RMSLE。
              </CardDescription>
            </CardHeader>
            <CardContent>
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
                      <TableCell>
                        <div className="font-medium">{m.title}</div>
                        <div className="text-muted-foreground text-xs">{m.note}</div>
                        {m.error ? (
                          <div className="text-destructive text-xs">{m.error}</div>
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
              {ranked?.[0] ? (
                <p className="mt-3 text-sm text-muted-foreground">
                  単体一位は {ranked[0].title}（{ranked[0].rmsle?.toFixed(4)}）。混合は検証で単体より悪ければ、重み付き平均が過学習していないかの確認材料になります。
                </p>
              ) : null}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>一番売れている系列の検証窓</CardTitle>
              <CardDescription>{result.preview.series_id}</CardDescription>
            </CardHeader>
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

          <div className="grid gap-3 md:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>LightGBM が使った列</CardTitle>
                <CardDescription>分割回数。上が効いている。</CardDescription>
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
                <CardTitle>本番提出で足すこと</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm text-muted-foreground">
                <p>1. 公式CSVを data/kaggle に置く。</p>
                <p>2. 同じ検証（末尾16日）で重みを決めてから全期間で再学習する（このアプリの LightGBM はそうしている）。</p>
                <p>3. 2016年4月の地震ウィンドウを落とす／印をつける。</p>
                <p>4. ファミリー別 LightGBM は次の一手。基盤モデルはゼロショットのまま比較する。</p>
              </CardContent>
            </Card>
          </div>
        </>
      ) : (
        <Alert>
          <AlertTitle>まだ結果がありません</AlertTitle>
          <AlertDescription>
            「予測を実行」でデモ24系列を回します。初回は Chronos-2 と TimesFM の重み読み込みで数分かかることがあります。
          </AlertDescription>
        </Alert>
      )}

      <Separator />
      <footer className="text-xs text-muted-foreground">
        対象コンペ: Store Sales — Time Series Forecasting。提出列は id,sales。
      </footer>
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
