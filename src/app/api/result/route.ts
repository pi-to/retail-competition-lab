import { readFile } from "node:fs/promises";
import path from "node:path";
import { outputDir } from "@/lib/cli";
import { DEFAULT_COMPETITION } from "@/lib/competitions";
import { isRunning } from "@/lib/run-state";

export const runtime = "nodejs";

async function readJson<T>(file: string): Promise<T | null> {
  try {
    return JSON.parse(await readFile(file, "utf8")) as T;
  } catch {
    return null;
  }
}

export async function GET(req: Request) {
  const slug = new URL(req.url).searchParams.get("competition") ?? DEFAULT_COMPETITION;
  const out = outputDir(slug);
  const [result, status, error, running] = await Promise.all([
    readJson<unknown>(path.join(out, "result.json")),
    readJson<unknown>(path.join(out, "status.json")),
    readJson<unknown>(path.join(out, "error.json")),
    isRunning(slug),
  ]);
  return Response.json({ result, status, error, running });
}
