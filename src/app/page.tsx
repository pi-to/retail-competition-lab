import { readFile } from "node:fs/promises";
import path from "node:path";
import { Overview } from "@/components/overview";
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

export default async function Home() {
  const content = getCompetition(DEFAULT_COMPETITION);
  const initial = await loadInitial(content.slug);
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
      />
      <Separator />
      <footer className="pb-6 text-xs text-muted-foreground">
        対象: {content.title}。提出は id,sales の2列。
      </footer>
    </main>
  );
}
