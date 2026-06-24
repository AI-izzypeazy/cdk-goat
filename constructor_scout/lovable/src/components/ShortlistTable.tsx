import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Card, CardContent, CardDescription, CardHeader, CardTitle,
} from "@/components/ui/card";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { ArrowRight, Loader2 } from "lucide-react";
import type { RegionResult } from "@/types";

export function ShortlistTable({
  data,
  busyDomain,
  onSelect,
}: {
  data: RegionResult;
  busyDomain?: string | null;
  onSelect: (domain: string) => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          Prospect shortlist — {data.country}
        </CardTitle>
        <CardDescription>
          {data.scanned} sites scanned, ranked by number of discovery gaps. Pick a target to deep-scan
          into a Problem → Constructor.io-solution brief.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-10">#</TableHead>
              <TableHead>Domain</TableHead>
              <TableHead className="text-center">Gaps</TableHead>
              <TableHead className="text-center">Opp</TableHead>
              <TableHead>Platform</TableHead>
              <TableHead>Incumbent</TableHead>
              <TableHead>Top gap</TableHead>
              <TableHead className="text-right">Action</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.shortlist.map((row) => (
              <TableRow key={row.domain}>
                <TableCell className="text-muted-foreground">{row.rank}</TableCell>
                <TableCell className="font-medium">
                  {row.domain}
                  {row.existing_customer && (
                    <Badge variant="secondary" className="ml-2">existing</Badge>
                  )}
                </TableCell>
                <TableCell className="text-center font-semibold">{row.gaps}</TableCell>
                <TableCell className="text-center">{row.opportunity}</TableCell>
                <TableCell className="text-muted-foreground">{row.platform}</TableCell>
                <TableCell className="text-muted-foreground">{row.incumbent}</TableCell>
                <TableCell className="max-w-[220px] truncate">{row.top_gap ?? "—"}</TableCell>
                <TableCell className="text-right">
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={!!busyDomain}
                    onClick={() => onSelect(row.domain)}
                  >
                    {busyDomain === row.domain ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <>
                        Deep scan <ArrowRight className="ml-1 h-3.5 w-3.5" />
                      </>
                    )}
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
