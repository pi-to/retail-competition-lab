import { readFile } from "node:fs/promises";
import path from "node:path";
import { outputDir } from "@/lib/cli";
import { DEFAULT_COMPETITION } from "@/lib/competitions";

export const runtime = "nodejs";

export async function GET(req: Request) {
  const slug = new URL(req.url).searchParams.get("competition") ?? DEFAULT_COMPETITION;
  try {
    const csv = await readFile(path.join(outputDir(slug), "submission.csv"));
    return new Response(csv, {
      headers: {
        "Content-Type": "text/csv; charset=utf-8",
        "Content-Disposition": `attachment; filename=${slug}-submission.csv`,
      },
    });
  } catch {
    return Response.json(
      { error: "まだ submission.csv がありません。先に実験を実行してください。" },
      { status: 404 }
    );
  }
}
