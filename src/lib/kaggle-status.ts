import { access, readFile } from "node:fs/promises";
import path from "node:path";
import { DEFAULT_COMPETITION } from "@/lib/competitions";
import type { KaggleStatus } from "@/lib/types";

/** Python 側 `retail_lab/competitions/<slug>/spec.py` と揃える。 */
const KAGGLE_SLUG: Record<string, string> = {
  "store-sales": "store-sales-time-series-forecasting",
};
const REQUIRED: Record<string, string[]> = {
  "store-sales": [
    "train.csv",
    "test.csv",
    "stores.csv",
    "oil.csv",
    "holidays_events.csv",
    "transactions.csv",
  ],
};

async function exists(file: string) {
  try {
    await access(file);
    return true;
  } catch {
    return false;
  }
}

/** `retail_lab/kaggle.py` の auth_header と同じ判断をする。 */
async function hasCredentials(root: string) {
  if (process.env.KAGGLE_API_TOKEN) return true;
  if (process.env.KAGGLE_KEY) return true;
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
        token?: string;
        api_token?: string;
      };
      if (blob.token || blob.api_token) return true;
      if (blob.username && blob.key) return true;
    } catch {
      // 読めないファイルは未設定として扱う
    }
  }
  return false;
}

/** 画面の初期表示用。Python を起動せずにファイルと環境変数だけ見る。 */
export async function readKaggleStatus(slug: string = DEFAULT_COMPETITION): Promise<KaggleStatus> {
  const root = process.cwd();
  const dir = path.join(root, "data", slug, "kaggle");
  const required = REQUIRED[slug] ?? [];
  const kaggleSlug = KAGGLE_SLUG[slug] ?? slug;
  const present = await Promise.all(
    required.map(async (name) => ({ name, ok: await exists(path.join(dir, name)) }))
  );
  const missing = present.filter((p) => !p.ok).map((p) => p.name);
  return {
    competition: kaggleSlug,
    ready: required.length > 0 && missing.length === 0,
    missing,
    has_credentials: await hasCredentials(root),
    rules_url: `https://www.kaggle.com/competitions/${kaggleSlug}/rules`,
    token_url: "https://www.kaggle.com/settings",
  };
}
