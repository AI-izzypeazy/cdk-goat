import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Search, Loader2 } from "lucide-react";

export interface RegionParams {
  country: string;
  verticals?: string[];
  per_vertical: number;
  max_sites: number;
}

export function RegionForm({
  loading,
  stage,
  onScan,
}: {
  loading: boolean;
  stage?: string;
  onScan: (p: RegionParams) => void;
}) {
  const [country, setCountry] = useState("");
  const [verticals, setVerticals] = useState("");
  const [maxSites, setMaxSites] = useState(20);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!country.trim()) return;
    onScan({
      country: country.trim(),
      verticals: verticals.trim() ? verticals.split(",").map((v) => v.trim()) : undefined,
      per_vertical: 5,
      max_sites: maxSites,
    });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Find prospects by region</CardTitle>
        <CardDescription>
          Enter a country. Scout discovers retail/ecommerce sites there, shallow-scans them,
          and ranks a shortlist by the number of product-discovery gaps Constructor.io can fix.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="country">Country / region</Label>
            <Input
              id="country"
              placeholder="e.g. United Kingdom"
              value={country}
              onChange={(e) => setCountry(e.target.value)}
              disabled={loading}
            />
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="verticals">Verticals (optional, comma-separated)</Label>
              <Input
                id="verticals"
                placeholder="fashion, beauty, electronics"
                value={verticals}
                onChange={(e) => setVerticals(e.target.value)}
                disabled={loading}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="max">Max sites to scan</Label>
              <Input
                id="max"
                type="number"
                min={1}
                max={50}
                value={maxSites}
                onChange={(e) => setMaxSites(Number(e.target.value))}
                disabled={loading}
              />
            </div>
          </div>
          <Button type="submit" disabled={loading || !country.trim()} className="w-full">
            {loading ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                {stage ? `Working — ${stage}…` : "Scanning…"}
              </>
            ) : (
              <>
                <Search className="mr-2 h-4 w-4" />
                Scan region
              </>
            )}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
