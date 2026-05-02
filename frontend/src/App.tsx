import { useEffect, useMemo, useState } from "react";
import UploadCsv from "./components/UploadCsv";
import PortfolioTable from "./components/PortfolioTable";
import AllocationChart from "./components/AllocationChart";
import RebalanceForm from "./components/RebalanceForm";
import BuyGuidance from "./components/BuyGuidance";
import { uploadPortfolio, fetchConfig } from "./services/api";
import type {
  AllocationBreakdown,
  ConfigSummary,
  PortfolioSnapshot,
  RebalanceResult,
  TargetAllocation,
} from "./types";
import "./styles/index.css";

export default function App() {
  const [portfolio, setPortfolio] = useState<PortfolioSnapshot | null>(null);
  const [allocation, setAllocation] = useState<AllocationBreakdown | null>(null);
  const [result, setResult] = useState<RebalanceResult | null>(null);
  const [config, setConfig] = useState<ConfigSummary | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  useEffect(() => {
    fetchConfig()
      .then(setConfig)
      .catch(() => {
        /* config fetch failure is non-fatal */
      });
  }, []);

  const handleUpload = async (file: File) => {
    setUploading(true);
    setUploadError(null);
    setPortfolio(null);
    setAllocation(null);
    setResult(null);
    try {
      const res = await uploadPortfolio(file);
      setPortfolio(res.portfolio);
      setAllocation(res.allocation);
    } catch (err: unknown) {
      setUploadError(err instanceof Error ? err.message : "Upload failed.");
    } finally {
      setUploading(false);
    }
  };

  const defaultTarget: TargetAllocation | null = config?.default_target ?? null;

  // bucket → sorted ticker list (for chart tooltip)
  const bucketSymbols = useMemo<Record<string, string[]>>(() => {
    if (!config) return {};
    const map: Record<string, string[]> = {};
    for (const [sym, bucket] of Object.entries(config.direct_mappings)) {
      (map[bucket] ??= []).push(sym);
    }
    for (const [sym, weights] of Object.entries(config.fractional_mappings)) {
      for (const bucket of Object.keys(weights)) {
        (map[bucket] ??= []).push(sym);
      }
    }
    for (const list of Object.values(map)) list.sort();
    return map;
  }, [config]);

  // symbol → bucket label (for holdings table)
  const symbolBucket = useMemo<Record<string, string>>(() => {
    if (!config) return {};
    const map: Record<string, string> = {};
    for (const [sym, bucket] of Object.entries(config.direct_mappings)) {
      map[sym] = bucket;
    }
    for (const [sym, weights] of Object.entries(config.fractional_mappings)) {
      map[sym] = Object.keys(weights).sort().join("/");
    }
    for (const sym of config.exclusions) {
      map[sym] = "Excl.";
    }
    return map;
  }, [config]);

  return (
    <div className="app">
      <header className="app-header">
        <h1>Investment Portfolio Rebalancer</h1>
        <p>Quarterly allocation analysis · VTI · VXUS · BND</p>
      </header>

      <main className="app-main">
        <UploadCsv onUpload={handleUpload} loading={uploading} error={uploadError} />

        {portfolio && allocation && (
          <>
            <div className="top-row">
              <AllocationChart breakdown={allocation} bucketSymbols={bucketSymbols} />
              <RebalanceForm
                allocation={allocation}
                defaultTarget={defaultTarget}
                onResult={setResult}
              />
            </div>

            {result && <BuyGuidance result={result} />}

            <PortfolioTable holdings={portfolio.holdings} totalValue={portfolio.total_value} symbolBucket={symbolBucket} />
          </>
        )}
      </main>
    </div>
  );
}
