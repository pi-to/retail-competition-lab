import { Report } from "@/components/report";
import { DEFAULT_COMPETITION, getCompetition } from "@/lib/competitions";

export const dynamic = "force-static";

export const metadata = {
  title: "Retail Lab — 実験の読み物版",
  description: "Kaggle Store Sales の実験履歴と、いま提出する版。読み物だけの静的ページ。",
};

export default function ReportPage() {
  return <Report content={getCompetition(DEFAULT_COMPETITION)} />;
}
