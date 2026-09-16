import { access, readFile } from "node:fs/promises";
import path from "node:path";
import type { KaggleStatus } from "@/lib/types";

const COMPETITION = "store-sales-time-series-forecasting";
const REQUIRED = [
  "train.csv",
  "test.csv",
  "stores.csv",
  "oil.csv",
  "holidays_events.csv",
  "transactions.csv",
];

async function exists(file: string) {
  try {
    await access(file);
    return true;
  } catch {
    return false;
  }
}

async function hasCredentials(root: string) {
  if (process.env.KAGGLE_USERNAME && process.env.KAGGLE_KEY) return true;
  const home = process.env.HOME ?? "";
  for (const candidate of [
    path.join(root, "kaggle.json"),
    home ? path.join(home, ".kaggle", "kaggle.json") : "",
  ].filter(Boolean)) {
    try {
      const blob = JSON.parse(await readFile(candidate, "utf8")) as {
        username?: string;
        key?: string;
      };
      if (blob.username && blob.key) return true;
    } catch {
      // 読めないファイルは未設定として扱う
    }
  }
  return false;
}

/** 画面の初期表示用。Python を起動せずにファイルと環境変数だけ見る。 */
export async function readKaggleStatus(): Promise<KaggleStatus> {
  const root = process.cwd();
  const dir = path.join(root, "data", "kaggle");
  const present = await Promise.all(
    REQUIRED.map(async (name) => ({ name, ok: await exists(path.join(dir, name)) }))
  );
  const missing = present.filter((p) => !p.ok).map((p) => p.name);
  return {
    competition: COMPETITION,
    ready: missing.length === 0,
    missing,
    has_credentials: await hasCredentials(root),
    rules_url: `https://www.kaggle.com/competitions/${COMPETITION}/rules`,
    token_url: "https://www.kaggle.com/settings",
  };
}
