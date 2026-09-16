import { readFile } from "node:fs/promises";
import path from "node:path";

export const runtime = "nodejs";

export async function GET() {
  const content = await readFile(
    path.join(process.cwd(), "docs/store-sales/developersio-draft.md"),
    "utf8"
  );
  return new Response(content, {
    headers: {
      "Content-Type": "text/markdown; charset=utf-8",
      "Content-Disposition": "attachment; filename=store-sales-developersio-draft.md",
    },
  });
}
