import { useEffect, useState } from "react";
import type { AllocationBreakdown, RebalanceResult, TargetAllocation } from "../types";
import { fetchRebalance } from "../services/api";

interface Props {
  allocation: AllocationBreakdown;
  defaultTarget: TargetAllocation | null;
  onResult: (result: RebalanceResult) => void;
}

export default function RebalanceForm({ allocation, defaultTarget, onResult }: Props) {
  const [amount, setAmount] = useState("");

  const initialBnd = defaultTarget ? defaultTarget.bnd : null;
  const initialStockPct = defaultTarget ? 100 - defaultTarget.bnd : null;
  const initialVxusStockPct =
    defaultTarget && initialStockPct && initialStockPct > 0
      ? (defaultTarget.vxus / initialStockPct) * 100
      : null;

  const [bnd, setBnd] = useState(initialBnd !== null ? String(initialBnd) : "");
  const [vxusOfStocks, setVxusOfStocks] = useState(
    initialVxusStockPct !== null ? String(initialVxusStockPct) : ""
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // update form when default target loads
  useEffect(() => {
    if (defaultTarget) {
      setBnd(String(defaultTarget.bnd));
      const stockPct = 100 - defaultTarget.bnd;
      const vxusStockPct = stockPct > 0 ? (defaultTarget.vxus / stockPct) * 100 : 0;
      setVxusOfStocks(String(vxusStockPct));
    }
  }, [defaultTarget]);

  const bndNum = parseFloat(bnd);
  const vxusStockNum = parseFloat(vxusOfStocks);
  const hasBnd = Number.isFinite(bndNum);
  const hasVxusStock = Number.isFinite(vxusStockNum);

  const stockPct = hasBnd ? 100 - bndNum : 0;
  const vxusWhole = hasBnd && hasVxusStock ? (stockPct * vxusStockNum) / 100 : 0;
  const vtiWhole = hasBnd && hasVxusStock ? stockPct - vxusWhole : 0;

  const bndOk = hasBnd && bndNum >= 0 && bndNum <= 100;
  const vxusStockOk = hasVxusStock && vxusStockNum >= 0 && vxusStockNum <= 100;
  const derivedOk = bndOk && vxusStockOk && vtiWhole >= -0.01 && vxusWhole >= -0.01;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    const amtNum = parseFloat(amount);
    if (!amtNum || amtNum <= 0) {
      setError("Enter a positive investment amount.");
      return;
    }
    if (!bndOk) {
      setError("BND target must be between 0% and 100%.");
      return;
    }
    if (!vxusStockOk) {
      setError("VXUS (of stocks) target must be between 0% and 100%.");
      return;
    }
    if (!derivedOk) {
      setError("Could not derive valid whole-portfolio targets from the inputs.");
      return;
    }

    setLoading(true);
    try {
      const result = await fetchRebalance(allocation, {
        investment_amount: amtNum,
        target: {
          vti: Math.max(0, vtiWhole),
          vxus: Math.max(0, vxusWhole),
          bnd: bndNum,
        },
      });
      onResult(result);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="card rebalance-card">
      <h2>Rebalance Calculator</h2>
      <p className="hint">Enter BND as a whole-portfolio target, then VXUS as a share of stocks.</p>

      <form onSubmit={handleSubmit} className="rebalance-form">
        <div className="form-row">
          <label>Investment Amount ($)</label>
          <input
            type="number"
            min="0.01"
            step="0.01"
            placeholder="e.g. 5000"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            required
          />
        </div>

        <fieldset>
          <legend>Inputs (%)</legend>
          <div className="alloc-inputs">
            {[
              { label: "BND (of total portfolio)", value: bnd, set: setBnd },
              { label: "VXUS (of stocks only)", value: vxusOfStocks, set: setVxusOfStocks },
            ].map(({ label, value, set }) => (
              <div key={label} className="alloc-row">
                <label>{label}</label>
                <input
                  type="number"
                  min="0"
                  max="100"
                  step="0.1"
                  value={value}
                  onChange={(e) => set(e.target.value)}
                  required
                />
                <span>%</span>
              </div>
            ))}
          </div>
          <p className={`sum-indicator ${derivedOk ? "ok" : "err"}`}>
            Derived Targets: VTI {vtiWhole.toFixed(1)}% · VXUS {vxusWhole.toFixed(1)}% · BND {hasBnd ? bndNum.toFixed(1) : "0.0"}%
          </p>
        </fieldset>

        {error && <p className="error-msg">{error}</p>}

        <button type="submit" disabled={loading} className="btn-primary">
          {loading ? "Calculating…" : "Calculate Buy Guidance"}
        </button>
      </form>
    </div>
  );
}
