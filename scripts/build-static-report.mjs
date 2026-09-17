/**
 * 読み物版だけを静的サイトに書き出す。
 *
 * 画面の本体は API ルート経由で Python と outputs/ を読むので、そのままでは
 * 静的化できない。ここでは作業コピーから API ルートと動的ページを外し、
 * /report だけを持つ小さなアプリとして書き出す。元のリポジトリは触らない。
 */
import { execFileSync } from "node:child_process";
import { copyFileSync, cpSync, existsSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

const root = process.cwd();
const basePath = process.env.PAGES_BASE_PATH ?? "";
const outDir = path.join(root, "out");

const work = mkdtempSync(path.join(tmpdir(), "retail-lab-report-"));
const skip = new Set([
  ".git",
  ".next",
  "node_modules",
  "out",
  "outputs",
  "data",
  ".venv",
  ".mypy_cache",
  ".pytest_cache",
  ".ruff_cache",
]);

try {
  cpSync(root, work, {
    recursive: true,
    filter: (src) => !skip.has(path.relative(root, src)),
  });
  cpSync(path.join(root, "node_modules"), path.join(work, "node_modules"), {
    recursive: true,
    verbatimSymlinks: true,
  });

  rmSync(path.join(work, "src/app/api"), { recursive: true, force: true });
  rmSync(path.join(work, "src/app/page.tsx"), { force: true });
  writeFileSync(
    path.join(work, "src/app/page.tsx"),
    'export { default, metadata } from "./report/page";\n',
    "utf8"
  );
  writeFileSync(
    path.join(work, "next.config.ts"),
    [
      'import type { NextConfig } from "next";',
      "",
      "const nextConfig: NextConfig = {",
      '  output: "export",',
      `  basePath: ${JSON.stringify(basePath)},`,
      "  trailingSlash: true,",
      "  images: { unoptimized: true },",
      "};",
      "",
      "export default nextConfig;",
      "",
    ].join("\n"),
    "utf8"
  );

  execFileSync("npx", ["next", "build"], {
    cwd: work,
    stdio: "inherit",
    env: { ...process.env, NEXT_TELEMETRY_DISABLED: "1" },
  });

  rmSync(outDir, { recursive: true, force: true });
  cpSync(path.join(work, "out"), outDir, { recursive: true });
  writeFileSync(path.join(outDir, ".nojekyll"), "", "utf8");
  // GitHub Pages と単純な静的サーバは /report をディレクトリとして開く。
  mkdirSync(path.join(outDir, "report"), { recursive: true });
  if (existsSync(path.join(outDir, "report.html")) && !existsSync(path.join(outDir, "report", "index.html"))) {
    copyFileSync(path.join(outDir, "report.html"), path.join(outDir, "report", "index.html"));
  }
  console.log(`静的な読み物版を書き出しました: ${outDir}`);
} finally {
  rmSync(work, { recursive: true, force: true });
}
