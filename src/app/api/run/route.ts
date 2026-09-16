import { spawn } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

export const runtime = "nodejs";
export const maxDuration = 300;

const running = new Map<string, Promise<void>>();

function rootDir() {
  return process.cwd();
}

async function runPython(source: "demo" | "kaggle") {
  const outDir = path.join(rootDir(), "outputs");
  await mkdir(outDir, { recursive: true });
  await writeFile(
    path.join(outDir, "status.json"),
    JSON.stringify({ step: "start", message: "起動しています", pct: 1 }),
    "utf8"
  );

  await new Promise<void>((resolve, reject) => {
    const child = spawn(
      "python3",
      [
        path.join(rootDir(), "python/run.py"),
        "--source",
        source,
        "--root",
        rootDir(),
        "--out",
        outDir,
      ],
      { cwd: rootDir(), env: { ...process.env, PYTHONUNBUFFERED: "1" } }
    );
    let stderr = "";
    child.stdout.on("data", (buf) => process.stdout.write(buf));
    child.stderr.on("data", (buf) => {
      stderr += buf.toString();
      process.stderr.write(buf);
    });
    child.on("error", reject);
    child.on("close", (code) => {
      if (code === 0) resolve();
      else reject(new Error(stderr || `python exited ${code}`));
    });
  });
}

export async function POST(req: Request) {
  const body = (await req.json().catch(() => ({}))) as { source?: string };
  const source = body.source === "kaggle" ? "kaggle" : "demo";
  const key = source;
  if (!running.has(key)) {
    const job = runPython(source).finally(() => running.delete(key));
    running.set(key, job);
  }
  try {
    await running.get(key);
    return Response.json({ ok: true, source });
  } catch (error) {
    const message = error instanceof Error ? error.message : "unknown error";
    return Response.json({ ok: false, error: message }, { status: 500 });
  }
}
