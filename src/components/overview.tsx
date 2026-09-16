import { Badge } from "@/components/ui/badge";
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
import type { CompetitionContent } from "@/lib/competitions";

export function Overview({ content }: { content: CompetitionContent }) {
  const { metric } = content;
  return (
    <div className="flex flex-col gap-10">
      <header className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-2">
          {content.badges.map((badge, i) => (
            <Badge key={badge} variant={i === 0 ? "default" : i === 1 ? "secondary" : "outline"}>
              {badge}
            </Badge>
          ))}
        </div>
        <h1 className="font-heading max-w-3xl text-3xl leading-tight tracking-tight sm:text-4xl">
          {content.headline}
        </h1>
        <p className="max-w-3xl text-lg text-muted-foreground">{content.oneLine}</p>
      </header>

      <section className="flex flex-col gap-3">
        <SectionTitle
          title="この問題の中身"
          sub="誰が困り、何を当て、当たると何が変わり、どれだけ効くか"
        />
        <div className="grid gap-3 sm:grid-cols-2">
          {content.pillars.map((p) => (
            <Card key={p.title}>
              <CardHeader>
                <CardDescription>{p.title}</CardDescription>
                <CardTitle className="text-base">{p.lead}</CardTitle>
              </CardHeader>
              <CardContent className="text-muted-foreground">{p.body}</CardContent>
            </Card>
          ))}
        </div>
      </section>

      <section className="flex flex-col gap-3">
        <SectionTitle title="規模" sub="予測は毎日この数だけ発生する" />
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {content.scale.map((s) => (
            <Card key={s.label} size="sm">
              <CardHeader>
                <CardDescription>{s.label}</CardDescription>
                <CardTitle className="font-mono text-xl">{s.value}</CardTitle>
              </CardHeader>
              <CardContent className="text-xs text-muted-foreground">{s.note}</CardContent>
            </Card>
          ))}
        </div>
      </section>

      <section className="flex flex-col gap-3">
        <SectionTitle
          title={`なぜ ${metric.name} で測るのが妥当か`}
          sub={metric.formulaPlain}
        />
        <div className="grid gap-3 md:grid-cols-2">
          <div className="flex flex-col gap-3">
            {metric.reasons.map((r, i) => (
              <Card key={r.title} size="sm">
                <CardHeader>
                  <CardTitle className="text-sm">
                    <span className="mr-2 font-mono text-muted-foreground">{i + 1}</span>
                    {r.title}
                  </CardTitle>
                </CardHeader>
                <CardContent className="text-sm text-muted-foreground">{r.body}</CardContent>
              </Card>
            ))}
          </div>
          <div className="flex flex-col gap-3">
            <Card>
              <CardHeader>
                <CardTitle className="text-sm">{metric.example.caption}</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-3">
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>状況</TableHead>
                        <TableHead className="text-right">実績</TableHead>
                        <TableHead className="text-right">予測</TableHead>
                        <TableHead className="text-right">ふつうの誤差</TableHead>
                        <TableHead className="text-right">{metric.name} の誤差</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {metric.example.rows.map((r) => (
                        <TableRow key={r.case}>
                          <TableCell className="min-w-36">{r.case}</TableCell>
                          <TableCell className="text-right font-mono">{r.actual}</TableCell>
                          <TableCell className="text-right font-mono">{r.pred}</TableCell>
                          <TableCell className="text-right font-mono">{r.rawError}</TableCell>
                          <TableCell className="text-right font-mono">{r.metricError}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
                <p className="text-sm text-muted-foreground">{metric.example.note}</p>
              </CardContent>
            </Card>
            <Card size="sm">
              <CardHeader>
                <CardDescription>指標の限界</CardDescription>
              </CardHeader>
              <CardContent className="text-sm text-muted-foreground">{metric.limits}</CardContent>
            </Card>
          </div>
        </div>
      </section>

      <section className="flex flex-col gap-3">
        <SectionTitle title="なぜ簡単に当たらないか" sub="この4つがスコアを決める" />
        <div className="grid gap-3 sm:grid-cols-2">
          {content.difficulty.map((d) => (
            <Card key={d.title} size="sm">
              <CardHeader>
                <CardTitle className="text-sm">{d.title}</CardTitle>
              </CardHeader>
              <CardContent className="text-sm text-muted-foreground">{d.body}</CardContent>
            </Card>
          ))}
        </div>
      </section>

      <section className="flex flex-col gap-3">
        <SectionTitle
          title="スコアの目安"
          sub={`${metric.name} は「典型的に何倍外すか」に読み替えられる`}
        />
        <Card>
          <CardContent className="flex flex-col gap-3">
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-20">{metric.name}</TableHead>
                    <TableHead>やり方</TableHead>
                    <TableHead className="text-right">外し方の目安</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {content.scoreGuide.map((s) => (
                    <TableRow key={s.score}>
                      <TableCell className="font-mono">{s.score}</TableCell>
                      <TableCell>{s.label}</TableCell>
                      <TableCell className="text-right text-muted-foreground">
                        {s.factor}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
            <p className="text-sm text-muted-foreground">{content.scoreNote}</p>
          </CardContent>
        </Card>
      </section>
    </div>
  );
}

function SectionTitle({ title, sub }: { title: string; sub: string }) {
  return (
    <div className="flex flex-col gap-1">
      <h2 className="font-heading text-xl tracking-tight">{title}</h2>
      <p className="text-sm text-muted-foreground">{sub}</p>
    </div>
  );
}
