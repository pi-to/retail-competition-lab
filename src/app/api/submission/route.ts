import { readFile } from "node:fs/promises";
import path from "node:path";
import { outputDir } from "@/lib/cli";
import { DEFAULT_COMPETITION } from "@/lib/competitions";

export const runtime = "nodejs";

const RUN_ID = /^[A-Za-z0-9._-]+$/;

function fileStem(raw: string | null, fallback: string): string {
  const cleaned = (raw ?? fallback)
    .replace(/[^A-Za-z0-9._-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80);
  return cleaned || fallback;
}

export async function GET(req: Request) {
  const url = new URL(req.url);
  const slug = url.searchParams.get("competition") ?? DEFAULT_COMPETITION;
  const run = url.searchParams.get("run");
  if (run && !RUN_ID.test(run)) {
    return Response.json({ error: "不正なRunです。" }, { status: 400 });
  }

  const csvPath = run
    ? path.join(outputDir(slug), "runs", run, "submission.csv")
    : path.join(outputDir(slug), "submission.csv");
  const stem = fileStem(url.searchParams.get("as"), run ? `${slug}-${run}` : `${slug}-champion`);

  try {
    const csv = await readFile(csvPath);
    return new Response(csv, {
      headers: {
        "Content-Type": "text/csv; charset=utf-8",
        "Content-Disposition": `attachment; filename="${stem}.csv"`,
      },
    });
  } catch {
    return Response.json(
      {
        error: run
          ? "この実験の提出CSVがこの環境にありません。"
          : "まだ submission.csv がありません。先に実験を実行してください。",
      },
      { status: 404 }
    );
  }
}
