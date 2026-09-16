import { spawn } from "node:child_process";
import path from "node:path";

export const runtime = "nodejs";

export type CliResult = { code: number; stdout: string; stderr: string };

/** Python は uv 経由で動かす（AGENTS.md の約束）。 */
export function runCli(args: string[]): Promise<CliResult> {
  const cwd = process.cwd();
  const env = {
    ...process.env,
    PYTHONUNBUFFERED: "1",
    PATH: `${process.env.HOME ?? ""}/.local/bin:${process.env.PATH ?? ""}`,
  };
  return new Promise((resolve, reject) => {
    const child = spawn("uv", ["run", "retail-lab", "--root", cwd, ...args], { cwd, env });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (buf) => {
      stdout += buf.toString();
      process.stdout.write(buf);
    });
    child.stderr.on("data", (buf) => {
      stderr += buf.toString();
      process.stderr.write(buf);
    });
    child.on("error", reject);
    child.on("close", (code) => resolve({ code: code ?? 1, stdout, stderr }));
  });
}

export function outputDir(slug: string) {
  return path.join(process.cwd(), "outputs", slug);
}
