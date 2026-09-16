import { spawn } from "node:child_process";
import path from "node:path";

export const runtime = "nodejs";
export const maxDuration = 900;

type PythonResult = { code: number; stdout: string; stderr: string };

function runPython(args: string[]): Promise<PythonResult> {
  return new Promise((resolve, reject) => {
    const child = spawn("python3", [path.join(process.cwd(), "python/kaggle_data.py"), ...args], {
      cwd: process.cwd(),
      env: { ...process.env, PYTHONUNBUFFERED: "1" },
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (buf) => (stdout += buf.toString()));
    child.stderr.on("data", (buf) => (stderr += buf.toString()));
    child.on("error", reject);
    child.on("close", (code) => resolve({ code: code ?? 1, stdout, stderr }));
  });
}

export async function GET() {
  const res = await runPython(["--status", "--root", process.cwd()]);
  try {
    return Response.json(JSON.parse(res.stdout));
  } catch {
    return Response.json({ error: res.stderr || "状態を取得できません" }, { status: 500 });
  }
}

export async function POST() {
  const res = await runPython(["--root", process.cwd()]);
  try {
    const parsed = JSON.parse(res.stdout) as { ok?: boolean };
    return Response.json(parsed, { status: parsed.ok ? 200 : 400 });
  } catch {
    return Response.json(
      { ok: false, error: res.stderr || "取得に失敗しました" },
      { status: 500 }
    );
  }
}
