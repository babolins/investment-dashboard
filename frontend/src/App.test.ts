import { render, screen, waitFor, within } from "@testing-library/svelte";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { UploadResponse } from "./types";
import App from "./App.svelte";
import { fetchConfig, fetchRebalance, uploadPortfolio } from "./services/api";
import { allocation, config, portfolio, rebalance } from "./test/fixtures";

vi.mock("./services/api", () => ({
  fetchConfig: vi.fn(),
  uploadPortfolio: vi.fn(),
  fetchRebalance: vi.fn(),
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

  it("uses the config for table bucket badges and chart tickers", async () => {
    vi.mocked(uploadPortfolio).mockResolvedValue(uploaded);
    const user = userEvent.setup();
    const { container } = render(App);
    await upload(container, user);
    await screen.findByText("Holdings");

    // Config loads independently of the upload; wait for it to reach the table.
    const spaxx = screen.getByText("SPAXX", { selector: "td.symbol" }).closest("tr") as HTMLElement;
    await waitFor(() => expect(within(spaxx).getByText("Excl.")).toBeInTheDocument());

    const chartPath = container.querySelector(".allocation-card path") as SVGPathElement;
    await user.hover(chartPath);
    expect(container.querySelector(".tooltip-tickers")).toHaveTextContent("BND");
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
});
