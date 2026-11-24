import { render, screen, waitFor, within } from "@testing-library/svelte";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import PortfolioTable from "./PortfolioTable.svelte";
import { setAssignment } from "../services/api";
import { config, portfolio, unassignedHolding } from "../test/fixtures";
import type { ConfigSummary, HoldingRow } from "../types";

// The pills inside the table import the API client.
vi.mock("../services/api", () => ({ setAssignment: vi.fn() }));

beforeEach(() => vi.resetAllMocks());

function row(symbol: string, overrides: Partial<HoldingRow> = {}): HoldingRow {
  return {
    symbol,
    description: `${symbol} fund`,
    quantity: 1,
    last_price: 1,
    current_value: 100,
    cost_basis: null,
    total_gain_loss: null,
    percent_of_account: 1,
    ...overrides,
  };
}

function symbolRow(symbol: string): HTMLElement {
  return screen.getByText(symbol, { selector: "td.symbol" }).closest("tr") as HTMLElement;
}

function symbols(): (string | null)[] {
  return screen
    .getAllByRole("row")
    .slice(1)
    .map((r) => within(r).getAllByRole("cell")[0].textContent);
}

function renderTable(
  holdings = portfolio.holdings,
  cfg: ConfigSummary | null = config,
  onConfigChange = vi.fn(),
) {
  return render(PortfolioTable, {
    props: { holdings, totalValue: portfolio.total_value, config: cfg, onConfigChange },
  });
}

describe("PortfolioTable", () => {
  it("shows the heading and total value", () => {
    renderTable();
    expect(screen.getByRole("heading", { name: "Holdings" })).toBeInTheDocument();
    expect(screen.getByText("$11,000.00").tagName).toBe("STRONG");
    expect(screen.getByText(/Total portfolio value:/)).toBeInTheDocument();
  });

  it("sorts by current value descending by default", () => {
    // VTI 6000, VXUS 3000, then BND and SPAXX tie at 1000 (order between them unspecified).
    renderTable();
    expect(symbols().slice(0, 2)).toEqual(["VTI", "VXUS"]);
    expect(screen.getByRole("columnheader", { name: /current value/i })).toHaveAttribute(
      "aria-sort",
      "descending",
    );
  });

  it("does not mutate the holdings prop", () => {
    const holdings = [row("B", { current_value: 1 }), row("A", { current_value: 2 })];
    renderTable(holdings);
    expect(holdings.map((h) => h.symbol)).toEqual(["B", "A"]);
  });

  it("toggles direction when the active header is clicked", async () => {
    const user = userEvent.setup();
    renderTable();
    const header = screen.getByRole("columnheader", { name: /current value/i });

    await user.click(screen.getByRole("button", { name: /current value/i }));
    expect(header).toHaveAttribute("aria-sort", "ascending");
    expect(symbols().slice(-2)).toEqual(["VXUS", "VTI"]);

    await user.click(screen.getByRole("button", { name: /current value/i }));
    expect(header).toHaveAttribute("aria-sort", "descending");
    expect(symbols().slice(0, 2)).toEqual(["VTI", "VXUS"]);
  });

  it("switches key on another header, starting descending", async () => {
    const user = userEvent.setup();
    renderTable();
    await user.click(screen.getByRole("button", { name: /symbol/i }));

    expect(screen.getByRole("columnheader", { name: /symbol/i })).toHaveAttribute(
      "aria-sort",
      "descending",
    );
    expect(screen.getByRole("columnheader", { name: /current value/i })).toHaveAttribute(
      "aria-sort",
      "none",
    );
    expect(symbols()).toEqual(["VXUS", "VTI", "SPAXX", "BND"]);

    await user.click(screen.getByRole("button", { name: /symbol/i }));
    expect(symbols()).toEqual(["BND", "SPAXX", "VTI", "VXUS"]);
  });

  it("leaves the Category column unsortable", () => {
    renderTable();
    expect(screen.queryByRole("button", { name: /^category/i })).toBeNull();
    expect(screen.getByRole("columnheader", { name: "Category" })).not.toHaveAttribute("aria-sort");
    expect(screen.queryByRole("columnheader", { name: /bucket/i })).toBeNull();
  });

  it("sorts a null gain as the lowest value", async () => {
    const user = userEvent.setup();
    renderTable();
    await user.click(screen.getByRole("button", { name: /gain\/loss/i }));
    // 1000, 0, -200, null
    expect(symbols()).toEqual(["VTI", "SPAXX", "VXUS", "BND"]);

    await user.click(screen.getByRole("button", { name: /gain\/loss/i }));
    expect(symbols()).toEqual(["BND", "VXUS", "SPAXX", "VTI"]);
  });

  it("keeps ordering sane when several gains are null", async () => {
    const user = userEvent.setup();
    renderTable([
      row("N1"),
      row("POS", { total_gain_loss: 5 }),
      row("N2"),
      row("NEG", { total_gain_loss: -5 }),
    ]);
    await user.click(screen.getByRole("button", { name: /gain\/loss/i }));
    const desc = symbols();
    expect(desc.slice(0, 2)).toEqual(["POS", "NEG"]);
    expect(desc.slice(2).sort()).toEqual(["N1", "N2"]);

    await user.click(screen.getByRole("button", { name: /gain\/loss/i }));
    const asc = symbols();
    expect(asc.slice(0, 2).sort()).toEqual(["N1", "N2"]);
    expect(asc.slice(2)).toEqual(["NEG", "POS"]);
  });

  it("formats gain/loss with sign, a dash for null, and colour classes", () => {
    renderTable();
    const cells = (symbol: string) => {
      const r = symbolRow(symbol);
      return within(r).getAllByRole("cell");
    };
    // columns: symbol, category, description, quantity, value, gain/loss, %
    expect(cells("VTI")[5]).toHaveTextContent("+$1,000.00");
    expect(cells("VTI")[5]).toHaveClass("gain");
    expect(cells("VXUS")[5]).toHaveTextContent("-$200.00");
    expect(cells("VXUS")[5]).toHaveClass("loss");
    expect(cells("SPAXX")[5]).toHaveTextContent("+$0.00");
    expect(cells("SPAXX")[5]).toHaveClass("gain");
    expect(cells("BND")[5]).toHaveTextContent("—");
    expect(cells("BND")[5]).not.toHaveClass("gain");
    expect(cells("BND")[5]).not.toHaveClass("loss");
  });

  it("formats quantity, value and percent of account", () => {
    renderTable();
    const r = symbolRow("BND");
    const cells = within(r).getAllByRole("cell");
    expect(cells[3]).toHaveTextContent("1,234.5");
    expect(cells[4]).toHaveTextContent("$1,000.00");
    expect(cells[6]).toHaveTextContent("9.09%");
  });

  it("shows each holding's category as a pill", () => {
    renderTable([...portfolio.holdings, row("FZROX", { current_value: 1 }), unassignedHolding]);
    const pill = (symbol: string) => within(symbolRow(symbol)).getByRole("button");

    expect(pill("VTI")).toHaveTextContent("US Stocks");
    expect(pill("FZROX")).toHaveTextContent("US Stocks 70% · International 30%");
    expect(pill("SPAXX")).toHaveTextContent("Excluded");
    expect(pill("MYSTERY")).toHaveTextContent("Unassigned");
  });

  it("shows a plain dash instead of a pill while config is not loaded", () => {
    renderTable(portfolio.holdings, null);
    const cell = within(symbolRow("VTI")).getAllByRole("cell")[1];
    expect(cell).toHaveTextContent("—");
    expect(within(cell).queryByRole("button")).toBeNull();
  });

  it("passes the saved config up through onConfigChange", async () => {
    const user = userEvent.setup();
    const updated: ConfigSummary = { ...config, exclusions: [...config.exclusions, "VTI"] };
    vi.mocked(setAssignment).mockResolvedValue(updated);
    const onConfigChange = vi.fn();
    renderTable(portfolio.holdings, config, onConfigChange);

    await user.click(within(symbolRow("VTI")).getByRole("button"));
    await user.click(screen.getByRole("checkbox", { name: "Exclude from allocation" }));
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(setAssignment).toHaveBeenCalledWith("VTI", { excluded: true });
    await waitFor(() => expect(onConfigChange).toHaveBeenCalledWith(updated));
  });

  it("keeps an open editor with its row when the table is re-sorted", async () => {
    const user = userEvent.setup();
    renderTable();
    await user.click(within(symbolRow("VTI")).getByRole("button"));
    await user.click(screen.getByRole("button", { name: /symbol/i }));

    const editor = screen.getByRole("checkbox", { name: "Exclude from allocation" });
    expect(symbolRow("VTI").contains(editor)).toBe(true);
  });
});
