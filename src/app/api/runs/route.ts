import { outputDir, runCli } from "@/lib/cli";
import { DEFAULT_COMPETITION } from "@/lib/competitions";

export const runtime = "nodejs";

function parse(stdout: string) {
  try {
    return JSON.parse(stdout) as Record<string, unknown>;
  } catch {
    return null;
  }
}

export async function GET(req: Request) {
  const slug = new URL(req.url).searchParams.get("competition") ?? DEFAULT_COMPETITION;
  const result = await runCli(["--competition", slug, "runs", "--json"]);
  const payload = parse(result.stdout);
  return payload
    ? Response.json(payload)
    : Response.json({ runs: [], tags: {}, error: result.stderr }, { status: 500 });
}

export async function POST(req: Request) {
  const body = (await req.json()) as {
    competition?: string;
    action?: "promote" | "tag";
    ref?: string;
    tag?: string;
  };
  const slug = body.competition ?? DEFAULT_COMPETITION;
  if (!body.ref) return Response.json({ error: "Runを指定してください。" }, { status: 400 });
  const args =
    body.action === "tag" && body.tag
      ? ["--competition", slug, "tag", body.tag, body.ref]
      : ["--competition", slug, "promote", body.ref];
  const result = await runCli(args);
  if (result.code !== 0) {
    return Response.json({ error: result.stderr || "操作に失敗しました。" }, { status: 400 });
  }
  return Response.json({ ok: true, output: parse(result.stdout), resultDir: outputDir(slug) });
}
