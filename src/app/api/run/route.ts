import { mkdir, open, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { spawn } from "node:child_process";
import { outputDir } from "@/lib/cli";
import { DEFAULT_COMPETITION } from "@/lib/competitions";
import { isRunning } from "@/lib/run-state";

export const runtime = "nodejs";

/**
 * 実験は数十分かかることがあるので、HTTP リクエストの中で待たない。
 * 起動だけして返し、画面は outputs/<slug>/status.json を読んで進捗を出す。
 */
export async function POST(req: Request) {
  const body = (await req.json().catch(() => ({}))) as { source?: string; competition?: string };
  const source = body.source === "kaggle" ? "kaggle" : "demo";
  const slug = body.competition ?? DEFAULT_COMPETITION;
  const out = outputDir(slug);

  if (await isRunning(slug)) {
    return Response.json({ started: true, alreadyRunning: true, competition: slug, source });
  }

  await mkdir(out, { recursive: true });
  await rm(path.join(out, "error.json"), { force: true });
  await writeFile(
    path.join(out, "status.json"),
    JSON.stringify({ step: "start", message: "起動しています", pct: 1 }),
    "utf8"
  );

  const log = await open(path.join(out, "run.log"), "w");
  const cwd = process.cwd();
  const child = spawn(
    "uv",
    ["run", "retail-lab", "--root", cwd, "--competition", slug, "run", "--source", source],
    {
      cwd,
      env: {
        ...process.env,
        PYTHONUNBUFFERED: "1",
        PATH: `${process.env.HOME ?? ""}/.local/bin:${process.env.PATH ?? ""}`,
      },
      detached: true,
      stdio: ["ignore", log.fd, log.fd],
    }
  );
  child.unref();
  await log.close();

  return Response.json({ started: true, competition: slug, source });
}
