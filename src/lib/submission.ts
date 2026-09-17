/** 提出CSVのダウンロードURL。落とすファイル名に実験名を入れる。 */
export function submissionHref(opts: {
  competition: string;
  runId?: string;
  as: string;
}): string {
  const params = new URLSearchParams({ competition: opts.competition, as: opts.as });
  if (opts.runId) params.set("run", opts.runId);
  return `/api/submission?${params.toString()}`;
}
