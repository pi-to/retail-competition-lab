import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import { Overview } from "@/components/overview";
import type { RunHistory } from "@/components/experiment-history";
import { StoreApp } from "@/components/store-app";
import { Separator } from "@/components/ui/separator";
import { DEFAULT_COMPETITION, getCompetition } from "@/lib/competitions";
import { isRunning } from "@/lib/run-state";
import type { Result, RunError, Status } from "@/lib/types";

export const dynamic = "force-dynamic";

async function loadInitial(slug: string) {
  const out = path.join(process.cwd(), "outputs", slug);
  const read = async <T,>(name: string): Promise<T | null> => {
    try {
      return JSON.parse(await readFile(path.join(out, name), "utf8")) as T;
    } catch {
      return null;
    }
  };
  const [result, status, error, running] = await Promise.all([
    read<Result>("result.json"),
    read<Status>("status.json"),
    read<RunError>("error.json"),
    isRunning(slug),
  ]);
  return { result, status, error, running };
}


async function loadRuns(slug: string): Promise<RunHistory> {
  const out = path.join(process.cwd(), "outputs", slug);
  const tags = (await readJson<Record<string, string>>(path.join(out, "tags.json"))) ?? {};
  let ids: string[] = [];
  try {
    ids = await readdir(path.join(out, "runs"));
  } catch {
    return { runs: [], tags };
  }
  const records = await Promise.all(
    ids.map((id) => readJson<RunHistory["runs"][number]>(path.join(out, "runs", id, "run.json")))
  );
  const runs = records
    .filter((run): run is RunHistory["runs"][number] => run !== null)
    .sort((a, b) => b.created_at.localeCompare(a.created_at));
  return { runs, tags };
}

async function readJson<T>(file: string): Promise<T | null> {
  try {
    return JSON.parse(await readFile(file, "utf8")) as T;
  } catch {
    return null;
  }
}

export default async function Home() {
  const content = getCompetition(DEFAULT_COMPETITION);
  const [initial, runHistory] = await Promise.all([
    loadInitial(content.slug),
    loadRuns(content.slug),
  ]);
  return (
    <main className="mx-auto flex w-full max-w-5xl flex-col gap-10 px-4 py-10 sm:px-6">
      <Overview content={content} />
      <Separator />
      <StoreApp
        content={content}
        initialResult={initial.result}
        initialStatus={initial.status}
        initialError={initial.error}
        initialRunning={initial.running}
        runHistory={runHistory}
      />
      <Separator />
      <footer className="pb-6 text-xs text-muted-foreground">
        対象: {content.title}。提出は id,sales の2列。
      </footer>
    </main>
  );
}
