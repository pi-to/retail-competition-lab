import storeSales from "@/lib/competitions/store-sales";
import type { CompetitionContent } from "@/lib/competitions/types";

/**
 * 扱っているコンペの一覧。Python 側 `retail_lab/registry.py` と slug を揃える。
 * コンペを足すときは、ここに1行と対応するファイルを追加する。
 */
export const COMPETITIONS: CompetitionContent[] = [storeSales];

export const DEFAULT_COMPETITION = storeSales.slug;

export function getCompetition(slug: string = DEFAULT_COMPETITION): CompetitionContent {
  const found = COMPETITIONS.find((c) => c.slug === slug);
  if (!found) throw new Error(`未登録のコンペです: ${slug}`);
  return found;
}

export type { CompetitionContent };
