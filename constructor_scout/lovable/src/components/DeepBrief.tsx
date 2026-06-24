import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Card, CardContent, CardDescription, CardHeader, CardTitle,
} from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { SeverityBadge } from "@/components/SeverityBadge";
import { ArrowLeft, ExternalLink, Copy } from "lucide-react";
import { toast } from "sonner";
import type { DeepResult } from "@/types";

export function DeepBrief({ data, onBack }: { data: DeepResult; onBack: () => void }) {
  const copyOutreach = () => {
    const text = `Subject: ${data.outreach.subject}\n\n${data.outreach.body}`;
    navigator.clipboard.writeText(text);
    toast.success("Outreach email copied");
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <Button variant="ghost" size="sm" onClick={onBack}>
          <ArrowLeft className="mr-2 h-4 w-4" /> Back to shortlist
        </Button>
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Badge variant="outline">priority {data.priority}</Badge>
          <span>opportunity {data.opportunity}/100</span>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-2xl">{data.domain}</CardTitle>
          <CardDescription>
            {data.platform} · incumbent discovery: {data.incumbent}
          </CardDescription>
        </CardHeader>
        {data.summary && (
          <CardContent>
            <p className="text-sm leading-relaxed">{data.summary}</p>
          </CardContent>
        )}
      </Card>

      <div>
        <h2 className="mb-3 text-lg font-semibold">
          Problems &amp; Constructor.io solutions ({data.findings.length})
        </h2>
        <div className="space-y-4">
          {data.findings.map((f, i) => (
            <Card key={f.code}>
              <CardHeader className="pb-3">
                <div className="flex items-center gap-2">
                  <span className="text-muted-foreground">{i + 1}.</span>
                  <SeverityBadge severity={f.severity} />
                  <CardTitle className="text-base">{f.title}</CardTitle>
                </div>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                <div>
                  <span className="font-semibold text-foreground">Problem. </span>
                  {f.problem}
                  {f.example && (
                    <p className="mt-1 italic text-muted-foreground">e.g. {f.example}</p>
                  )}
                </div>
                <div>
                  <span className="font-semibold text-foreground">Solution (Constructor.io). </span>
                  <span className="font-medium">{f.capability}</span> — {f.solution}
                  {f.capability_docs && (
                    <a
                      href={f.capability_docs}
                      target="_blank"
                      rel="noreferrer"
                      className="ml-1 inline-flex items-center text-primary hover:underline"
                    >
                      docs <ExternalLink className="ml-0.5 h-3 w-3" />
                    </a>
                  )}
                </div>
                {f.evidence.length > 0 && (
                  <div className="rounded-md bg-muted p-2 text-xs text-muted-foreground">
                    <span className="font-medium">Evidence: </span>
                    {f.evidence.join("; ")}
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      </div>

      {(data.outreach.subject || data.outreach.body) && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">Suggested outreach</CardTitle>
              <Button variant="outline" size="sm" onClick={copyOutreach}>
                <Copy className="mr-2 h-3.5 w-3.5" /> Copy
              </Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <p className="font-medium">Subject: {data.outreach.subject}</p>
            <Separator />
            <pre className="whitespace-pre-wrap font-sans text-sm">{data.outreach.body}</pre>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
