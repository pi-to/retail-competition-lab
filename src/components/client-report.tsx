import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { ModelRow, Result } from "@/lib/types";

const pct = (x: number | undefined) => (x === undefined ? "—" : `${(x * 100).toFixed(1)}%`);
const signedPct = (x: number | undefined) =>
  x === undefined ? "—" : `${x > 0 ? "+" : ""}${(x * 100).toFixed(1)}%`;

/** 非エンジニア向け。指標名ではなく「何が起きたか」で並べる。 */
export function ClientReport({ result }: { result: Result }) {
  const report = result.report;
  const rows = result.models.filter((m) => m.status === "ok");
  const blend = rows.find((m) => m.id === "blend");
  const others = rows.filter((m) => m.id !== "blend");

  return (
    <div className="flex flex-col gap-4">
      {report ? (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {report.data_usage.map((u) => (
            <Card key={u.label} size="sm">
              <CardHeader>
                <CardDescription>{u.label}</CardDescription>
                <CardTitle className="text-sm">{u.value}</CardTitle>
              </CardHeader>
              <CardContent className="text-xs text-muted-foreground">{u.detail}</CardContent>
            </Card>
          ))}
        </div>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>隠した16日間の答え合わせ</CardTitle>
          <CardDescription>
            誤差率が小さいほど当たっている。偏りは全体として多めか少なめか。
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>やり方</TableHead>
                  <TableHead className="text-right">誤差率</TableHead>
                  <TableHead className="text-right">偏り</TableHead>
                  <TableHead className="text-right">欠品側</TableHead>
                  <TableHead className="text-right">RMSLE</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {[...others, ...(blend ? [blend] : [])].map((m) => (
                  <ReportRow key={m.id} model={m} highlight={m.id === "blend"} />
                ))}
              </TableBody>
            </Table>
          </div>
          <p className="text-sm text-muted-foreground">
            一番下が実際に採用した予測です。上の各行は、それを作るために比べた候補です。
          </p>
        </CardContent>
      </Card>

      {report ? (
        <div className="grid gap-3 md:grid-cols-2">
          {report.interpretation.map((item) => (
            <Card key={item.title} size="sm">
              <CardHeader>
                <CardTitle className="text-sm">{item.title}</CardTitle>
              </CardHeader>
              <CardContent className="text-sm text-muted-foreground">{item.body}</CardContent>
            </Card>
          ))}
        </div>
      ) : null}

      {report ? (
        <Card size="sm">
          <CardHeader>
            <CardDescription>言葉の意味</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-2 sm:grid-cols-2">
            {report.glossary.map((g) => (
              <p key={g.term} className="text-sm text-muted-foreground">
                <span className="font-medium text-foreground">{g.term}</span>：{g.body}
              </p>
            ))}
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}

function ReportRow({ model, highlight }: { model: ModelRow; highlight: boolean }) {
  return (
    <TableRow className={highlight ? "bg-muted/50 font-medium" : undefined}>
      <TableCell className="min-w-44">
        <div>{model.title}</div>
        {model.org ? (
          <div className="text-xs text-muted-foreground">{model.org}</div>
        ) : null}
      </TableCell>
      <TableCell className="text-right font-mono">{pct(model.wape)}</TableCell>
      <TableCell className="text-right font-mono">{signedPct(model.bias)}</TableCell>
      <TableCell className="text-right font-mono">{pct(model.under_rate)}</TableCell>
      <TableCell className="text-right font-mono text-muted-foreground">
        {model.rmsle?.toFixed(4) ?? "—"}
      </TableCell>
    </TableRow>
  );
}
