import { render, screen } from "@testing-library/svelte";
import { describe, expect, it, vi } from "vitest";
import type { ConfigSummary } from "./types";
import App from "./App.svelte";
import { fetchConfig } from "./services/api";

vi.mock("./services/api", () => ({
  fetchConfig: vi.fn(),
  uploadPortfolio: vi.fn(),
  fetchRebalance: vi.fn(),
}));

const config: ConfigSummary = {
  direct_mappings: { VTI: "VTI" },
  fractional_mappings: {},
  exclusions: [],
  primary_symbols: { VTI: "VTI", VXUS: "VXUS", BND: "BND" },
  default_target: null,
};

describe("App", () => {
  it("renders the page and upload sections and loads config once", async () => {
    vi.mocked(fetchConfig).mockResolvedValue(config);
    render(App);

    expect(
      screen.getByRole("heading", { level: 1, name: "Investment Portfolio Rebalancer" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Upload Portfolio" })).toBeInTheDocument();
    expect(fetchConfig).toHaveBeenCalledTimes(1);
  });
});
