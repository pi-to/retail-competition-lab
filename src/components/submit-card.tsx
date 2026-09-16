"use client";

import { useState } from "react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { Result } from "@/lib/types";

type Receipt = {
  message: string;
  ref?: number;
  submitted_at: string;
  description: string;
};

export function SubmitCard({ result }: { result: Result }) {
  const [confirming, setConfirming] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  const [error, setError] = useState<string | null>(null);
  const blend = result.models.find((model) => model.id === "blend");
  const ready = result.source === "kaggle" && !submitting;
  const description = `Retail Lab | RMSLE ${blend?.rmsle?.toFixed(4) ?? "unknown"} | ${new Date().toISOString().slice(0, 10)}`;

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
          <Button onClick={() => setConfirming(true)} disabled={!ready}>
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
            <div className="flex flex-wrap gap-2">
              <Button onClick={() => void submit()} disabled={submitting}>
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
