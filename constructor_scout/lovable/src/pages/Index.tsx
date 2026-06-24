import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { Telescope } from "lucide-react";

import { RegionForm, type RegionParams } from "@/components/RegionForm";
import { ShortlistTable } from "@/components/ShortlistTable";
import { DeepBrief } from "@/components/DeepBrief";
import { deepScan, scanRegion } from "@/lib/api";
import type { DeepResult, RegionResult } from "@/types";

const Index = () => {
  const [stage, setStage] = useState<string>();
  const [region, setRegion] = useState<RegionResult | null>(null);
  const [brief, setBrief] = useState<DeepResult | null>(null);

  const regionMut = useMutation({
    mutationFn: (p: RegionParams) => scanRegion(p, setStage),
    onSuccess: (data) => {
      setRegion(data);
      setBrief(null);
      if (!data.shortlist.length) toast.warning("No sites found for that region.");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const deepMut = useMutation({
    mutationFn: (domain: string) => deepScan(domain, setStage),
    onSuccess: (data) => setBrief(data),
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b">
        <div className="mx-auto flex max-w-5xl items-center gap-3 px-4 py-5">
          <Telescope className="h-7 w-7 text-primary" />
          <div>
            <h1 className="text-xl font-bold leading-tight">Constructor Scout</h1>
            <p className="text-sm text-muted-foreground">
              Find retail/ecommerce prospects with product-discovery gaps Constructor.io can fix.
            </p>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-5xl space-y-6 px-4 py-8">
        {brief ? (
          <DeepBrief data={brief} onBack={() => setBrief(null)} />
        ) : (
          <>
            <RegionForm
              loading={regionMut.isPending}
              stage={regionMut.isPending ? stage : undefined}
              onScan={(p) => regionMut.mutate(p)}
            />
            {region && (
              <ShortlistTable
                data={region}
                busyDomain={deepMut.isPending ? deepMut.variables : null}
                onSelect={(domain) => deepMut.mutate(domain)}
              />
            )}
          </>
        )}
      </main>
    </div>
  );
};

export default Index;
