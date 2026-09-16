import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { outputDir, runCli } from "@/lib/cli";
import { DEFAULT_COMPETITION } from "@/lib/competitions";

export const runtime = "nodejs";
export const maxDuration = 900;

/** コンペごとに1本だけ走らせる。連打しても同じ実行を待つ。 */
const running = new Map<string, Promise<void>>();

async function runExperiment(slug: string, source: "demo" | "kaggle") {
  const out = outputDir(slug);
  await mkdir(out, { recursive: true });
  await writeFile(
    path.join(out, "status.json"),
    JSON.stringify({ step: "start", message: "起動しています", pct: 1 }),
    "utf8"
  );
  const result = await runCli(["--competition", slug, "run", "--source", source]);
  if (result.code !== 0) {
    throw new Error(result.stderr.trim() || `実行が失敗しました（終了コード ${result.code}）`);
  }
}

export async function POST(req: Request) {
  const body = (await req.json().catch(() => ({}))) as { source?: string; competition?: string };
  const source = body.source === "kaggle" ? "kaggle" : "demo";
  const slug = body.competition ?? DEFAULT_COMPETITION;
  const key = `${slug}:${source}`;

  if (!running.has(key)) {
    running.set(
      key,
      runExperiment(slug, source).finally(() => running.delete(key))
    );
  }
  try {
    await running.get(key);
    return Response.json({ ok: true, competition: slug, source });
  } catch (error) {
    const message = error instanceof Error ? error.message : "unknown error";
    return Response.json({ ok: false, error: message }, { status: 500 });
  }
}
