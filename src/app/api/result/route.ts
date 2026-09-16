import { readFile } from "node:fs/promises";
import path from "node:path";
import { outputDir } from "@/lib/cli";
import { DEFAULT_COMPETITION } from "@/lib/competitions";

export const runtime = "nodejs";

export async function GET(req: Request) {
  const slug = new URL(req.url).searchParams.get("competition") ?? DEFAULT_COMPETITION;
  const out = outputDir(slug);
  const [result, status] = await Promise.all([
    readFile(path.join(out, "result.json"), "utf8").catch(() => null),
    readFile(path.join(out, "status.json"), "utf8").catch(() => null),
  ]);
  return Response.json({
    result: result ? JSON.parse(result) : null,
    status: status ? JSON.parse(status) : null,
  });
}
