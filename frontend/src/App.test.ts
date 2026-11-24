import { render, screen, waitFor, within } from "@testing-library/svelte";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AllocationBreakdown, ConfigSummary, UploadResponse } from "./types";
import App from "./App.svelte";
import {
  deleteCategory,
  fetchAllocation,
  fetchConfig,
  fetchRebalance,
  uploadPortfolio,
} from "./services/api";
import { allocation, config, portfolio, rebalance } from "./test/fixtures";

vi.mock("./services/api", () => ({
  fetchConfig: vi.fn(),
  uploadPortfolio: vi.fn(),
  fetchRebalance: vi.fn(),
  fetchAllocation: vi.fn(),
  createCategory: vi.fn(),
  updateCategory: vi.fn(),
  deleteCategory: vi.fn(),
  setAssignment: vi.fn(),
}));

const uploaded: UploadResponse = { portfolio, allocation };

function csv() {
  return new File(["a,b"], "portfolio.csv", { type: "text/csv" });
}

async function upload(container: HTMLElement, user: ReturnType<typeof userEvent.setup>) {
  const input = container.querySelector("input[type=file]") as HTMLInputElement;
  await user.upload(input, csv());
}

async function calculate(user: ReturnType<typeof userEvent.setup>) {
  // Targets prefill from the config, so wait for it before submitting.
  await screen.findByLabelText("US Stocks % of portfolio");
  await user.type(screen.getByLabelText(/investment amount/i), "1000");
  await user.click(screen.getByRole("button", { name: /calculate buy guidance/i }));
}

describe("App", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(fetchConfig).mockResolvedValue(config);
  });

  it("renders the page and upload sections and loads config once", async () => {
    render(App);

    expect(
      screen.getByRole("heading", { level: 1, name: "Investment Portfolio Rebalancer" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Upload Portfolio" })).toBeInTheDocument();
    expect(fetchConfig).toHaveBeenCalledTimes(1);
  });

  it("shows the subtitle without the old fixed symbols", () => {
    const { container } = render(App);
    const header = container.querySelector("header") as HTMLElement;
    expect(header).toHaveTextContent("Quarterly allocation analysis");
    expect(header).not.toHaveTextContent("VXUS");
  });

  it("shows the category manager once the config loads, before any upload", async () => {
    render(App);
    expect(await screen.findByRole("heading", { name: "Categories" })).toBeInTheDocument();
    expect(screen.queryByText("Asset Allocation")).toBeNull();
  });

  it("shows no category manager when the config fails to load", async () => {
    vi.mocked(fetchConfig).mockRejectedValue(new Error("config down"));
    render(App);
    await waitFor(() => expect(fetchConfig).toHaveBeenCalled());
    expect(screen.queryByRole("heading", { name: "Categories" })).toBeNull();
  });

  it("shows nothing portfolio-related before an upload", () => {
    render(App);
    expect(screen.queryByText("Asset Allocation")).toBeNull();
    expect(screen.queryByText("Rebalance Calculator")).toBeNull();
    expect(screen.queryByText("Holdings")).toBeNull();
    expect(screen.queryByText("Buy Guidance")).toBeNull();
  });

  it("treats a config failure as non-fatal", async () => {
    vi.mocked(fetchConfig).mockRejectedValue(new Error("config down"));
    vi.mocked(uploadPortfolio).mockResolvedValue(uploaded);
    const user = userEvent.setup();
    const { container } = render(App);

    expect(screen.getByRole("heading", { name: "Upload Portfolio" })).toBeInTheDocument();
    expect(screen.queryByText(/config down/)).toBeNull();

    await upload(container, user);
    expect(await screen.findByText("Asset Allocation")).toBeInTheDocument();
  });

  it("shows the chart, rebalance form and holdings after a successful upload", async () => {
    vi.mocked(uploadPortfolio).mockResolvedValue(uploaded);
    const user = userEvent.setup();
    const { container } = render(App);
    await upload(container, user);

    expect(await screen.findByText("Asset Allocation")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Rebalance Calculator" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Holdings" })).toBeInTheDocument();
    expect(uploadPortfolio).toHaveBeenCalledWith(
      expect.objectContaining({ name: "portfolio.csv" }),
    );
    expect(screen.queryByText("Buy Guidance")).toBeNull();
  });

  it("uses the config for table pills and chart tickers", async () => {
    vi.mocked(uploadPortfolio).mockResolvedValue(uploaded);
    const user = userEvent.setup();
    const { container } = render(App);
    await upload(container, user);
    await screen.findByText("Holdings");

    // Config loads independently of the upload; wait for it to reach the table.
    const spaxx = screen.getByText("SPAXX", { selector: "td.symbol" }).closest("tr") as HTMLElement;
    await waitFor(() => expect(within(spaxx).getByText("Excluded")).toBeInTheDocument());

    const chartPath = container.querySelector(".allocation-card path") as SVGPathElement;
    await user.hover(chartPath);
    expect(container.querySelector(".tooltip-tickers")).toHaveTextContent("FZROX, ITOT, VTI");
  });

  it("shows the upload error and no portfolio data when the upload fails", async () => {
    vi.mocked(uploadPortfolio).mockRejectedValue(new Error("Bad CSV"));
    const user = userEvent.setup();
    const { container } = render(App);
    await upload(container, user);

    expect(await screen.findByText("Bad CSV")).toBeInTheDocument();
    expect(screen.queryByText("Asset Allocation")).toBeNull();
    expect(screen.queryByText("Holdings")).toBeNull();
  });

  it("shows Buy Guidance after the rebalance form is submitted", async () => {
    vi.mocked(uploadPortfolio).mockResolvedValue(uploaded);
    vi.mocked(fetchRebalance).mockResolvedValue(rebalance);
    const user = userEvent.setup();
    const { container } = render(App);
    await upload(container, user);
    await screen.findByText("Rebalance Calculator");

    await calculate(user);

    expect(await screen.findByRole("heading", { name: "Buy Guidance" })).toBeInTheDocument();
    expect(fetchRebalance).toHaveBeenCalledTimes(1);
    expect(screen.getByText("$697.67")).toBeInTheDocument();
  });

  it("clears the previous Buy Guidance and holdings as soon as a new upload starts", async () => {
    vi.mocked(uploadPortfolio).mockResolvedValueOnce(uploaded);
    vi.mocked(fetchRebalance).mockResolvedValue(rebalance);
    const user = userEvent.setup();
    const { container } = render(App);
    await upload(container, user);
    await screen.findByText("Rebalance Calculator");
    await calculate(user);
    await screen.findByRole("heading", { name: "Buy Guidance" });

    // Second upload stays pending, so anything missing was cleared up front.
    vi.mocked(uploadPortfolio).mockReturnValueOnce(new Promise(() => {}));
    await upload(container, user);

    await waitFor(() => expect(screen.queryByText("Buy Guidance")).toBeNull());
    expect(screen.queryByText("Holdings")).toBeNull();
    expect(screen.queryByText("Asset Allocation")).toBeNull();
  });

  describe("config changes", () => {
    const twoCategories: ConfigSummary = { ...config, categories: config.categories.slice(0, 2) };
    const refreshed: AllocationBreakdown = {
      ...allocation,
      categories: allocation.categories.slice(0, 2),
      included_value: 9000,
      unassigned_value: 1000,
    };
    const legendRows = (container: HTMLElement) => container.querySelectorAll(".legend-row");
    const deleteBonds = (user: ReturnType<typeof userEvent.setup>) =>
      user.click(screen.getByRole("button", { name: "Delete Bonds" }));

    async function loaded() {
      vi.mocked(uploadPortfolio).mockResolvedValue(uploaded);
      vi.mocked(fetchRebalance).mockResolvedValue(rebalance);
      const user = userEvent.setup();
      const view = render(App);
      await upload(view.container, user);
      await screen.findByText("Asset Allocation");
      return { ...view, user };
    }

    it("re-fetches the allocation for the loaded portfolio and clears Buy Guidance", async () => {
      vi.mocked(deleteCategory).mockResolvedValue(twoCategories);
      vi.mocked(fetchAllocation).mockResolvedValue(refreshed);
      const { container, user } = await loaded();
      await calculate(user);
      await screen.findByRole("heading", { name: "Buy Guidance" });

      await deleteBonds(user);

      await waitFor(() => expect(fetchAllocation).toHaveBeenCalledTimes(1));
      expect(fetchAllocation).toHaveBeenCalledWith(portfolio);
      await waitFor(() => expect(legendRows(container)).toHaveLength(2));
      expect(screen.queryByRole("heading", { name: "Buy Guidance" })).toBeNull();
      expect(container.querySelector(".unassigned-note")).toHaveTextContent("$1,000.00");
      expect(screen.queryByLabelText("Bonds % of portfolio")).toBeNull();
    });

    it("does not fetch an allocation when no portfolio is loaded", async () => {
      vi.mocked(deleteCategory).mockResolvedValue(twoCategories);
      const user = userEvent.setup();
      render(App);
      await screen.findByRole("heading", { name: "Categories" });

      await deleteBonds(user);

      await waitFor(() => expect(deleteCategory).toHaveBeenCalledTimes(1));
      expect(screen.queryByText("Bonds")).toBeNull();
      expect(fetchAllocation).not.toHaveBeenCalled();
    });

    it("ignores an out-of-order refresh response", async () => {
      const oneCategory: ConfigSummary = { ...config, categories: config.categories.slice(0, 1) };
      vi.mocked(deleteCategory)
        .mockResolvedValueOnce(twoCategories)
        .mockResolvedValueOnce(oneCategory);
      let resolveFirst!: (a: AllocationBreakdown) => void;
      let resolveSecond!: (a: AllocationBreakdown) => void;
      vi.mocked(fetchAllocation)
        .mockReturnValueOnce(new Promise((r) => (resolveFirst = r)))
        .mockReturnValueOnce(new Promise((r) => (resolveSecond = r)));
      const latest: AllocationBreakdown = {
        ...allocation,
        categories: allocation.categories.slice(0, 1),
      };
      const { container, user } = await loaded();

      await deleteBonds(user);
      await waitFor(() => expect(fetchAllocation).toHaveBeenCalledTimes(1));
      await user.click(screen.getByRole("button", { name: "Delete International" }));
      await waitFor(() => expect(fetchAllocation).toHaveBeenCalledTimes(2));

      resolveSecond(latest);
      await waitFor(() => expect(legendRows(container)).toHaveLength(1));
      resolveFirst(refreshed);
      await new Promise((r) => setTimeout(r, 20));
      expect(legendRows(container)).toHaveLength(1);
    });

    it("shows an alert when the refresh fails", async () => {
      vi.mocked(deleteCategory).mockResolvedValue(twoCategories);
      vi.mocked(fetchAllocation).mockRejectedValue(new Error("boom"));
      const { user } = await loaded();

      await deleteBonds(user);

      expect(await screen.findByText(/Could not refresh allocation: boom/)).toBeInTheDocument();
      expect(screen.getByRole("heading", { name: "Holdings" })).toBeInTheDocument();
    });
  });
});
