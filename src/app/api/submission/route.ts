import { readFile } from "node:fs/promises";
import path from "node:path";

export const runtime = "nodejs";

export async function GET() {
  const file = path.join(process.cwd(), "outputs", "submission.csv");
  try {
    const csv = await readFile(file);
    return new Response(csv, {
      headers: {
        "Content-Type": "text/csv; charset=utf-8",
        "Content-Disposition": "attachment; filename=submission.csv",
      },
    });
  } catch {
    return Response.json({ error: "まだ submission.csv がありません。先に実験を実行してください。" }, { status: 404 });
  }
}
