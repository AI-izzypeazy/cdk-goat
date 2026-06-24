import { Badge } from "@/components/ui/badge";
import type { Severity } from "@/types";

const STYLES: Record<Severity, string> = {
  critical: "bg-red-600 hover:bg-red-600 text-white",
  high: "bg-orange-500 hover:bg-orange-500 text-white",
  medium: "bg-amber-400 hover:bg-amber-400 text-black",
  low: "bg-sky-500 hover:bg-sky-500 text-white",
  info: "bg-muted text-muted-foreground",
};

export function SeverityBadge({ severity }: { severity: Severity }) {
  return <Badge className={STYLES[severity]}>{severity}</Badge>;
}
