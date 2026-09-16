import { readFile } from "node:fs/promises";
import path from "node:path";
import { outputDir, runCli } from "@/lib/cli";
import { DEFAULT_COMPETITION } from "@/lib/competitions";

export const runtime = "nodejs";
export const maxDuration = 300;

function parse(stdout: string) {
  try {
    return JSON.parse(stdout) as Record<string, unknown>;
  } catch {
    return null;
  }
}

/** 提出できる状態か（トークン権限とコンペ参加）を先に確かめる。提出はしない。 */
export async function GET(req: Request) {
  const url = new URL(req.url);
  const slug = url.searchParams.get("competition") ?? DEFAULT_COMPETITION;

  if (url.searchParams.get("receipt") === "1") {
    try {
      const receipt = JSON.parse(
        await readFile(path.join(outputDir(slug), "last_submission.json"), "utf8")
      );
      return Response.json({ receipt });
    } catch {
      return Response.json({ receipt: null });
    }
  }

  const result = await runCli(["--competition", slug, "preflight"]);
  const parsed = parse(result.stdout);
  if (!parsed) {
    return Response.json(
      { ok: false, message: result.stderr.trim() || "確認できませんでした。" },
      { status: 500 }
    );
  }
  return Response.json(parsed);
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

  const parsed = parse(result.stdout) as { ok?: boolean } | null;
  if (!parsed) {
    return Response.json(
      { ok: false, error: result.stderr.trim() || "提出に失敗しました。" },
      { status: 500 }
    );
  }
  return Response.json(parsed, { status: parsed.ok ? 200 : 400 });
}
