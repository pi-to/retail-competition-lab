import { readFile } from "node:fs/promises";
import path from "node:path";
import { outputDir, runCli } from "@/lib/cli";
import { DEFAULT_COMPETITION } from "@/lib/competitions";

export const runtime = "nodejs";
export const maxDuration = 300;

export async function GET(req: Request) {
  const slug = new URL(req.url).searchParams.get("competition") ?? DEFAULT_COMPETITION;
  try {
    const receipt = JSON.parse(
      await readFile(path.join(outputDir(slug), "last_submission.json"), "utf8")
    );
    return Response.json({ receipt });
  } catch {
    return Response.json({ receipt: null });
  }
}

export async function POST(req: Request) {
  const body = (await req.json().catch(() => ({}))) as {
    competition?: string;
    message?: string;
  };
  const slug = body.competition ?? DEFAULT_COMPETITION;
  const message = (body.message ?? "Retail Lab submission").trim().slice(0, 500);
  const result = await runCli([
    "--competition",
    slug,
    "submit",
    "--message",
    message || "Retail Lab submission",
  ]);

  try {
    const parsed = JSON.parse(result.stdout) as { ok?: boolean };
    return Response.json(parsed, { status: parsed.ok ? 200 : 400 });
  } catch {
    return Response.json(
      { ok: false, error: result.stderr.trim() || "提出に失敗しました。" },
      { status: 500 }
    );
  }
}
