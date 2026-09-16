"use client";

import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
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
import type { Result } from "@/lib/types";

type Receipt = {
  message: string;
  ref?: number;
  submitted_at: string;
  description: string;
};

type Preflight = { ok: boolean; message: string; hint?: string };

export function SubmitCard({ result }: { result: Result }) {
  const [confirming, setConfirming] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [preflight, setPreflight] = useState<Preflight | null>(null);
  const [checking, setChecking] = useState(false);
  const blend = result.models.find((model) => model.id === "blend");
  const activeModels = result.models.filter(
    (model) => model.id !== "blend" && (model.weight ?? 0) > 0
  );
  const rejectedModels = result.models.filter(
    (model) => model.id !== "blend" && model.status === "ok" && (model.weight ?? 0) === 0
  );
  const scoreChart = result.models
    .filter((model) => model.id !== "blend" && model.status === "ok")
    .map((model) => ({
      name: model.title,
      rmsle: model.rmsle ?? 0,
      used: (model.weight ?? 0) > 0,
    }));
  const featureChart = result.feature_importance.slice(0, 8).map((feature) => ({
    name: feature.feature,
    importance: feature.gain,
  }));
  const ready = result.source === "kaggle" && !submitting;
  const description = `Retail Lab | RMSLE ${blend?.rmsle?.toFixed(4) ?? "unknown"} | ${new Date().toISOString().slice(0, 10)}`;

  /** 確認画面を開くときに、権限と参加状態を先に確かめる。提出はしない。 */
  async function review() {
    setConfirming(true);
    setChecking(true);
    setPreflight(null);
    try {
      const response = await fetch(
        `/api/kaggle/submit?competition=${result.competition}`,
        { cache: "no-store" }
      );
      setPreflight((await response.json()) as Preflight);
    } catch (err) {
      setPreflight({
        ok: false,
        message: err instanceof Error ? err.message : "確認できませんでした。",
      });
    } finally {
      setChecking(false);
    }
  }

  async function submit() {
    setSubmitting(true);
    setError(null);
    try {
      const response = await fetch("/api/kaggle/submit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ competition: result.competition, message: description }),
      });
      const data = (await response.json()) as Receipt & {
        ok?: boolean;
        error?: string;
        hint?: string;
      };
      if (!response.ok || !data.ok) {
        setError([data.error ?? "提出に失敗しました。", data.hint].filter(Boolean).join("\n"));
        return;
      }
      setReceipt(data);
      setConfirming(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "提出に失敗しました。");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Kaggleへ提出</CardTitle>
        <CardDescription>
          公式データで作った28,512行を検査してから送ります。Kaggleへの提出は取り消せません。
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {!confirming ? (
          <Button onClick={() => void review()} disabled={!ready}>
            {result.source === "kaggle" ? "提出内容を確認" : "公式データで再計算してください"}
          </Button>
        ) : (
          <div className="flex flex-col gap-3 rounded-lg border p-3">
            <div className="grid gap-2 text-sm sm:grid-cols-3">
              <div>
                <p className="text-muted-foreground">コンペ</p>
                <p>{result.title}</p>
              </div>
              <div>
                <p className="text-muted-foreground">検証 RMSLE</p>
                <p className="font-mono">{blend?.rmsle?.toFixed(4) ?? "—"}</p>
              </div>
              <div>
                <p className="text-muted-foreground">提出行数</p>
                <p className="font-mono">28,512</p>
              </div>
            </div>
            <p className="text-sm text-muted-foreground">
              送信前に id の一致・重複・欠損・負の売上を自動検査します。
            </p>

            <div className="grid gap-3 lg:grid-cols-2">
              <section className="rounded-lg bg-muted/50 p-3">
                <h3 className="mb-2 font-medium">採用したモデル</h3>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>モデル</TableHead>
                      <TableHead className="text-right">検証RMSLE</TableHead>
                      <TableHead className="text-right">重み</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {activeModels.map((model) => (
                      <TableRow key={model.id}>
                        <TableCell>
                          {model.title}
                          {model.checkpoint ? (
                            <span className="block font-mono text-xs text-muted-foreground">
                              {model.checkpoint}
                            </span>
                          ) : null}
                        </TableCell>
                        <TableCell className="text-right font-mono">
                          {model.rmsle?.toFixed(4)}
                        </TableCell>
                        <TableCell className="text-right font-mono">
                          {((model.weight ?? 0) * 100).toFixed(1)}%
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
                <p className="mt-2 text-xs text-muted-foreground">
                  予測値は log(1+売上) の空間で混ぜています。今回の重みは検証窓で
                  RMSLE が最小になるよう、負にならない範囲で決めました。
                </p>
                {rejectedModels.length > 0 ? (
                  <p className="mt-2 text-xs text-muted-foreground">
                    不採用：{rejectedModels.map((model) => model.title).join("、")}
                    （混ぜると検証スコアが悪化したため重み0）
                  </p>
                ) : null}
              </section>

              <section className="rounded-lg bg-muted/50 p-3">
                <h3 className="mb-2 font-medium">ローカル検証</h3>
                <dl className="grid gap-2 text-sm">
                  <div>
                    <dt className="text-muted-foreground">学習</dt>
                    <dd>2013-01-01〜2017-07-30（2,979,504行）</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">答え合わせ</dt>
                    <dd>末尾16日・2017-07-31〜08-15（28,512行）を完全に隠す</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">未来漏洩の防止</dt>
                    <dd>売上ラグは予測期間以上の16・21・28・35日前だけ</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">本番予測</dt>
                    <dd>検証を終えた後、08-15までの全実績を使って08-16〜31を予測</dd>
                  </div>
                </dl>
              </section>

              <section className="rounded-lg bg-muted/50 p-3">
                <h3 className="mb-2 font-medium">LightGBMの特徴量</h3>
                <ul className="space-y-1 text-sm text-muted-foreground">
                  <li>売上：16・21・28・35日前、16日前からの7日/28日平均</li>
                  <li>販売施策：プロモーション数と log(1+プロモーション数)</li>
                  <li>カレンダー：曜日、日、月、週、週末、給料日、国/地域の祝日</li>
                  <li>外部環境：原油価格と7日前の原油価格</li>
                  <li>店舗：店舗番号、商品ファミリー、店舗タイプ、クラスター</li>
                </ul>
                <p className="mt-2 text-xs text-muted-foreground">
                  実際の重要度上位：
                  {result.feature_importance
                    .slice(0, 6)
                    .map((feature) => feature.feature)
                    .join("、")}
                </p>
              </section>

              <section className="rounded-lg bg-muted/50 p-3">
                <h3 className="mb-2 font-medium">カテゴリ処理と基盤モデル</h3>
                <p className="text-sm text-muted-foreground">
                  ワンホット化はしていません。店舗番号・商品ファミリー・店舗タイプ・
                  クラスターは LightGBM のネイティブカテゴリ型として渡し、木が最適な
                  分け方を直接学習します。
                </p>
                <p className="mt-2 text-sm text-muted-foreground">
                  Chronos-2 は直近540日の売上系列と、未来にも分かるプロモ・原油・祝日・
                  給料日をゼロショットで読みます。TimesFM 2.5 は売上系列だけで比較し、
                  今回は混ぜると悪化したため不採用です。
                </p>
              </section>
            </div>

            <div className="grid gap-3 lg:grid-cols-2">
              <section className="rounded-lg border p-3">
                <h3 className="font-medium">モデル別 RMSLE</h3>
                <p className="mb-2 text-xs text-muted-foreground">
                  低いほど良い。青は提出に採用、灰色は比較のみ。
                </p>
                <div className="h-56">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={scoreChart} layout="vertical" margin={{ left: 28, right: 16 }}>
                      <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                      <XAxis type="number" domain={[0, 0.7]} tick={{ fontSize: 11 }} />
                      <YAxis
                        type="category"
                        dataKey="name"
                        width={90}
                        tick={{ fontSize: 11 }}
                      />
                      <Tooltip formatter={(value) => Number(value).toFixed(4)} />
                      <Bar dataKey="rmsle" radius={[0, 4, 4, 0]}>
                        {scoreChart.map((item) => (
                          <Cell key={item.name} fill={item.used ? "#2563eb" : "#a1a1aa"} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </section>

              <section className="rounded-lg border p-3">
                <h3 className="font-medium">LightGBM 特徴量重要度</h3>
                <p className="mb-2 text-xs text-muted-foreground">
                  木が分岐に使った回数。上ほど予測判断に多く使われた。
                </p>
                <div className="h-56">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={featureChart} layout="vertical" margin={{ left: 56, right: 16 }}>
                      <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                      <XAxis type="number" tick={{ fontSize: 11 }} />
                      <YAxis
                        type="category"
                        dataKey="name"
                        width={118}
                        tick={{ fontSize: 10 }}
                      />
                      <Tooltip />
                      <Bar dataKey="importance" fill="#7c3aed" radius={[0, 4, 4, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </section>
            </div>

            {checking ? (
              <p className="text-sm text-muted-foreground">提出できる状態か確認しています…</p>
            ) : null}
            {preflight && !preflight.ok ? (
              <Alert variant="destructive">
                <AlertTitle>いまは提出できません</AlertTitle>
                <AlertDescription className="flex flex-col gap-2">
                  <span>{preflight.message}</span>
                  {preflight.hint ? <span>{preflight.hint}</span> : null}
                  <span className="flex flex-wrap gap-3 text-xs">
                    <a
                      className="underline"
                      href="https://www.kaggle.com/competitions/store-sales-time-series-forecasting/rules"
                      target="_blank"
                      rel="noreferrer"
                    >
                      コンペに参加する（Join Competition）
                    </a>
                    <a
                      className="underline"
                      href="https://www.kaggle.com/settings"
                      target="_blank"
                      rel="noreferrer"
                    >
                      トークンを作り直す
                    </a>
                    <a
                      className="underline"
                      href={`/api/submission?competition=${result.competition}`}
                    >
                      CSVを落として手で提出する
                    </a>
                  </span>
                </AlertDescription>
              </Alert>
            ) : null}
            <div className="flex flex-wrap gap-2">
              <Button
                onClick={() => void submit()}
                disabled={submitting || checking || (preflight ? !preflight.ok : false)}
              >
                {submitting ? "提出中…" : "この内容でKaggleへ提出"}
              </Button>
              <Button variant="outline" onClick={() => setConfirming(false)} disabled={submitting}>
                戻る
              </Button>
            </div>
          </div>
        )}

        {receipt ? (
          <Alert>
            <AlertTitle>提出を受け付けました</AlertTitle>
            <AlertDescription>
              {receipt.message}
              {receipt.ref ? `（提出ID: ${receipt.ref}）` : ""}
            </AlertDescription>
          </Alert>
        ) : null}
        {error ? (
          <Alert variant="destructive">
            <AlertTitle>提出できませんでした</AlertTitle>
            <AlertDescription className="whitespace-pre-wrap">{error}</AlertDescription>
          </Alert>
        ) : null}
      </CardContent>
    </Card>
  );
}
