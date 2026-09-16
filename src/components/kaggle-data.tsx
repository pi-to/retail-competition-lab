"use client";

import { useState } from "react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { KaggleStatus } from "@/lib/types";

export function KaggleData({
  initialStatus,
  onReady,
}: {
  initialStatus: KaggleStatus;
  onReady?: () => void;
}) {
  const [status, setStatus] = useState<KaggleStatus>(initialStatus);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ message: string; hint?: string } | null>(null);

  async function load() {
    const res = await fetch("/api/kaggle", { cache: "no-store" });
    if (res.ok) setStatus((await res.json()) as KaggleStatus);
  }

  async function download() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/kaggle", { method: "POST" });
      const data = (await res.json()) as { ok?: boolean; error?: string; hint?: string };
      if (!data.ok) setError({ message: data.error ?? "取得に失敗しました", hint: data.hint });
      else onReady?.();
      await load();
    } catch (err) {
      setError({ message: err instanceof Error ? err.message : "取得に失敗しました" });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2">
          公式データ
          <Badge variant={status.ready ? "default" : "outline"}>
            {status.ready ? "取得済み" : "未取得"}
          </Badge>
        </CardTitle>
        <CardDescription>
          Kaggle の API から <code>data/kaggle/</code> に直接ダウンロードします。
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={() => void download()} disabled={busy || status.ready}>
            {busy ? "ダウンロード中…" : status.ready ? "ダウンロード済み" : "Kaggle から取得"}
          </Button>
          {!status.has_credentials ? (
            <Button variant="outline" asChild>
              <a href={status.token_url} target="_blank" rel="noreferrer">
                APIトークンを作る
              </a>
            </Button>
          ) : null}
          <Button variant="ghost" asChild>
            <a href={status.rules_url} target="_blank" rel="noreferrer">
              コンペ規約に同意する
            </a>
          </Button>
        </div>

        {!status.has_credentials ? (
          <Alert>
            <AlertTitle>認証情報の設定が必要です</AlertTitle>
            <AlertDescription>
              Kaggle の Settings で API トークンを作り、リポジトリ直下の <code>.env.local</code> に
              <code>KAGGLE_USERNAME</code> と <code>KAGGLE_KEY</code> を書くか、ダウンロードした{" "}
              <code>kaggle.json</code> をリポジトリ直下に置いて開発サーバーを再起動してください。
              初回はコンペページで Join Competition（規約同意）も必要です。
            </AlertDescription>
          </Alert>
        ) : null}

        {!status.ready && status.missing.length > 0 && status.has_credentials ? (
          <p className="text-sm text-muted-foreground">
            不足しているファイル: {status.missing.join(", ")}
          </p>
        ) : null}

        {error ? (
          <Alert variant="destructive">
            <AlertTitle>取得に失敗しました</AlertTitle>
            <AlertDescription className="whitespace-pre-wrap">
              {error.message}
              {error.hint ? `\n${error.hint}` : ""}
            </AlertDescription>
          </Alert>
        ) : null}
      </CardContent>
    </Card>
  );
}
