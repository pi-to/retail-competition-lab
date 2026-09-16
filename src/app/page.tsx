import { readFile } from "node:fs/promises";
import path from "node:path";
import { StoreApp } from "@/components/store-app";
import type { Result, Status } from "@/lib/types";

export const dynamic = "force-dynamic";

async function loadInitial() {
  const out = path.join(process.cwd(), "outputs");
  try {
    const [result, status] = await Promise.all([
      readFile(path.join(out, "result.json"), "utf8").catch(() => null),
      readFile(path.join(out, "status.json"), "utf8").catch(() => null),
    ]);
    return {
      result: result ? (JSON.parse(result) as Result) : null,
      status: status ? (JSON.parse(status) as Status) : null,
    };
  } catch {
    return { result: null, status: null };
  }
}

export default async function Home() {
  const initial = await loadInitial();
  return (
    <main className="flex-1 bg-background">
      <StoreApp initialResult={initial.result} initialStatus={initial.status} />
    </main>
  );
}
