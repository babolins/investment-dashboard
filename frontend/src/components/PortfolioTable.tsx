import { useMemo, useState } from "react";
import type { HoldingRow } from "../types";

interface Props {
  holdings: HoldingRow[];
  totalValue: number;
  symbolBucket?: Record<string, string>;
}

type SortKey = keyof HoldingRow;
type SortDir = "asc" | "desc";

const fmt = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
const fmtPct = (n: number) => n.toFixed(2) + "%";
const fmtGain = (n: number | null) =>
  n == null ? "—" : (n >= 0 ? "+" : "") + fmt.format(n);

export default function PortfolioTable({ holdings, totalValue, symbolBucket = {} }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>("current_value");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const sorted = useMemo(() => {
    return [...holdings].sort((a, b) => {
      const av = a[sortKey] ?? -Infinity;
      const bv = b[sortKey] ?? -Infinity;
      if (typeof av === "string" && typeof bv === "string") {
        return sortDir === "asc" ? av.localeCompare(bv) : bv.localeCompare(av);
      }
      return sortDir === "asc" ? (av as number) - (bv as number) : (bv as number) - (av as number);
    });
  }, [holdings, sortKey, sortDir]);

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  };

  const arrow = (key: SortKey) => (sortKey === key ? (sortDir === "asc" ? " ▲" : " ▼") : "");

  return (
    <div className="card">
      <h2>Holdings</h2>
      <p className="hint">Total portfolio value: <strong>{fmt.format(totalValue)}</strong></p>
      <div className="table-wrapper">
        <table className="holdings-table">
          <thead>
            <tr>
              <th onClick={() => toggleSort("symbol")}>Symbol{arrow("symbol")}</th>
              <th>Bucket</th>
              <th onClick={() => toggleSort("description")}>Description{arrow("description")}</th>
              <th onClick={() => toggleSort("quantity")}>Quantity{arrow("quantity")}</th>
              <th onClick={() => toggleSort("current_value")}>Current Value{arrow("current_value")}</th>
              <th onClick={() => toggleSort("total_gain_loss")}>Total Gain/Loss{arrow("total_gain_loss")}</th>
              <th onClick={() => toggleSort("percent_of_account")}>% of Account{arrow("percent_of_account")}</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((h) => (
              <tr key={h.symbol}>
                <td className="symbol">{h.symbol}</td>
                <td><span className={`bucket-badge bucket-badge--${(symbolBucket[h.symbol] ?? "").toLowerCase().replace("/", "-")}`}>{symbolBucket[h.symbol] ?? "—"}</span></td>
                <td className="desc">{h.description}</td>
                <td className="num">{h.quantity.toLocaleString()}</td>
                <td className="num">{fmt.format(h.current_value)}</td>
                <td className={`num ${h.total_gain_loss == null ? "" : h.total_gain_loss >= 0 ? "gain" : "loss"}`}>
                  {fmtGain(h.total_gain_loss)}
                </td>
                <td className="num">{fmtPct(h.percent_of_account)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
