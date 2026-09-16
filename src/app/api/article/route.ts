import { readFile } from "node:fs/promises";
import path from "node:path";
import {
  championMarkdown,
  experimentTableMarkdown,
  rejectedMarkdown,
} from "@/lib/competitions/store-sales-experiments";

export const runtime = "nodejs";

/** 草稿の散文はファイル、数字は実験データ。手で写した表が古くなるのを防ぐ。 */
export async function GET() {
  const skeleton = await readFile(
    path.join(process.cwd(), "docs/store-sales/developersio-draft.md"),
    "utf8"
  );
  const content = skeleton
    .replace("<!-- EXPERIMENTS_TABLE -->", experimentTableMarkdown())
    .replace("<!-- CHAMPION -->", championMarkdown())
    .replace("<!-- REJECTED -->", rejectedMarkdown());
  return new Response(content, {
    headers: {
      "Content-Type": "text/markdown; charset=utf-8",
      "Content-Disposition": "attachment; filename=store-sales-developersio-draft.md",
    },
  });
}
