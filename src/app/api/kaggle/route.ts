import { runCli } from "@/lib/cli";
import { DEFAULT_COMPETITION } from "@/lib/competitions";

export const runtime = "nodejs";
export const maxDuration = 900;

function parse(stdout: string) {
  try {
    return JSON.parse(stdout) as Record<string, unknown>;
  } catch {
    return null;
  }
}

export async function GET(req: Request) {
  const slug = new URL(req.url).searchParams.get("competition") ?? DEFAULT_COMPETITION;
  const res = await runCli(["--competition", slug, "status"]);
  const parsed = parse(res.stdout);
  if (!parsed) {
    return Response.json({ error: res.stderr || "状態を取得できません" }, { status: 500 });
  }
  return Response.json(parsed);
}

export async function POST(req: Request) {
  const body = (await req.json().catch(() => ({}))) as { competition?: string };
  const slug = body.competition ?? DEFAULT_COMPETITION;
  const res = await runCli(["--competition", slug, "fetch"]);
  const parsed = parse(res.stdout) as { ok?: boolean } | null;
  if (!parsed) {
    return Response.json(
      { ok: false, error: res.stderr || "取得に失敗しました" },
      { status: 500 }
    );
  }
  return Response.json(parsed, { status: parsed.ok ? 200 : 400 });
}
