import { readFile } from "node:fs/promises";
import path from "node:path";

export const runtime = "nodejs";

export async function GET() {
  const out = path.join(process.cwd(), "outputs");
  try {
    const [result, status] = await Promise.all([
      readFile(path.join(out, "result.json"), "utf8").catch(() => null),
      readFile(path.join(out, "status.json"), "utf8").catch(() => null),
    ]);
    return Response.json({
      result: result ? JSON.parse(result) : null,
      status: status ? JSON.parse(status) : null,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "unknown error";
    return Response.json({ result: null, status: null, error: message }, { status: 500 });
  }
}
