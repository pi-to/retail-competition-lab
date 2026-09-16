import { readFile } from "node:fs/promises";
import path from "node:path";
import { outputDir } from "@/lib/cli";

/** 実験プロセスが生きているか。CLI が書く pid ファイルで判断する。 */
export async function isRunning(slug: string): Promise<boolean> {
  try {
    const pid = Number.parseInt(await readFile(path.join(outputDir(slug), "run.pid"), "utf8"), 10);
    if (!Number.isFinite(pid)) return false;
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}
