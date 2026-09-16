import { readFile } from "node:fs/promises";
import path from "node:path";
import { Overview } from "@/components/overview";
import { StoreApp } from "@/components/store-app";
import { Separator } from "@/components/ui/separator";
import { readKaggleStatus } from "@/lib/kaggle-status";
import type { Result, Status } from "@/lib/types";

export const dynamic = "force-dynamic";

async function loadInitial() {
  const out = path.join(process.cwd(), "outputs");
  const [result, status] = await Promise.all([
    readFile(path.join(out, "result.json"), "utf8").catch(() => null),
    readFile(path.join(out, "status.json"), "utf8").catch(() => null),
  ]);
  return {
    result: result ? (JSON.parse(result) as Result) : null,
    status: status ? (JSON.parse(status) as Status) : null,
  };
}

export default async function Home() {
  const [initial, kaggleStatus] = await Promise.all([loadInitial(), readKaggleStatus()]);
  return (
    <main className="mx-auto flex w-full max-w-5xl flex-col gap-10 px-4 py-10 sm:px-6">
      <Overview />
      <Separator />
      <StoreApp
        initialResult={initial.result}
        initialStatus={initial.status}
        kaggleStatus={kaggleStatus}
      />
      <Separator />
      <footer className="pb-6 text-xs text-muted-foreground">
        対象: Kaggle Store Sales — Time Series Forecasting。提出は id,sales の2列。
      </footer>
    </main>
  );
}
