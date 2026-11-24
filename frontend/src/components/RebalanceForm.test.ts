import { render, screen, waitFor, within } from "@testing-library/svelte";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fetchRebalance } from "../services/api";
import { allocation, config, nestedConfig, rebalance } from "../test/fixtures";
import type { Category, ConfigSummary, RebalanceResult } from "../types";
import RebalanceForm from "./RebalanceForm.svelte";

vi.mock("../services/api", () => ({ fetchRebalance: vi.fn() }));
const mockFetch = vi.mocked(fetchRebalance);

const BUTTON = "Calculate Buy Guidance";
const AMOUNT_MESSAGE = "Enter a positive investment amount.";
const RANGE_MESSAGE = "Top level: each share must be between 0% and 100%.";

const US = "US Stocks % of portfolio";
const INTL = "International % of portfolio";
const BONDS = "Bonds % of portfolio";

// Nested labels: Stocks and Bonds at the top level, the two stock funds inside Stocks.
const STOCKS = "Stocks % of portfolio";
const US_IN = "US Stocks % of Stocks";
const INTL_IN = "International % of Stocks";
const BONDS_TOP = "Bonds % of portfolio";

// nestedConfig with the Stocks and Bonds defaults removed, so typing is always a change.
const blankNested: ConfigSummary = {
  ...nestedConfig,
  categories: nestedConfig.categories.map((c) =>
    c.name === "Stocks" || c.name === "Bonds" ? { ...c, target: null } : c,
  ),
};

const twoFlat: ConfigSummary = { ...config, categories: config.categories.slice(0, 2) };

function renderForm(cfg: ConfigSummary = config) {
  const onResult = vi.fn();
  const view = render(RebalanceForm, { props: { allocation, config: cfg, onResult } });
  return {
    ...view,
    onResult,
    user: userEvent.setup(),
    amount: screen.getByLabelText("Investment Amount ($)"),
    levelErrors: () => view.container.querySelectorAll(".sum-indicator.err"),
  };
}

type Form = ReturnType<typeof renderForm>;

async function fill(user: Form["user"], input: HTMLElement, value: string) {
  await user.clear(input);
  if (value) await user.type(input, value);
}

const submit = (user: Form["user"]) => user.click(screen.getByRole("button", { name: BUTTON }));
const input = (label: string) => screen.getByLabelText(label);
const readout = (percent: string) => screen.queryByText(`= ${percent} of portfolio`);

beforeEach(() => vi.resetAllMocks());

describe("RebalanceForm", () => {
  describe("flat config", () => {
    it("renders the heading, amount input and one labelled input per category", () => {
      const { amount } = renderForm();
      expect(screen.getByRole("heading", { name: "Rebalance Calculator" })).toBeInTheDocument();
      expect(screen.getByText("Targets (%)")).toBeInTheDocument();
      expect(amount).toHaveValue(null);
      expect(screen.getByRole("button", { name: BUTTON })).toBeEnabled();
      expect(screen.getAllByRole("spinbutton")).toHaveLength(4); // amount + 3 categories
      for (const label of [US, INTL, BONDS]) expect(input(label)).toBeInTheDocument();
    });

    it("fills each input from the category target with no errors", () => {
      const { levelErrors } = renderForm();
      expect(input(US)).toHaveValue(48);
      expect(input(INTL)).toHaveValue(32);
      expect(input(BONDS)).toHaveValue(20);
      expect(levelErrors()).toHaveLength(0);
    });

    it("leaves inputs empty and reports the total for categories without a target", () => {
      const cfg = { ...config, categories: config.categories.map((c) => ({ ...c, target: null })) };
      renderForm(cfg);
      expect(input(US)).toHaveValue(null);
      expect(input(BONDS)).toHaveValue(null);
      expect(screen.getByText("Top level: must add up to 100% (currently 0.0%).")).toBeVisible();
    });

    it("shows inputs when the categories arrive after mount", async () => {
      const { rerender, levelErrors } = renderForm({ ...config, categories: [] });
      expect(screen.queryByLabelText(US)).toBeNull();
      await rerender({ config });
      expect(input(US)).toHaveValue(48);
      expect(input(BONDS)).toHaveValue(20);
      expect(levelErrors()).toHaveLength(0);
    });
  });

  describe("pair fill", () => {
    it("fills the other of two top-level nodes", async () => {
      const { user } = renderForm(twoFlat);
      await fill(user, input(US), "60");
      expect(input(INTL)).toHaveValue(40);
      await fill(user, input(INTL), "25");
      expect(input(US)).toHaveValue(75);
    });

    it("leaves the sibling alone for an out-of-range or cleared value", async () => {
      const { user } = renderForm(twoFlat);
      // "-5" is out of range from its first keystroke ("150" would pass through "1" and "15").
      await fill(user, input(US), "-5");
      expect(input(INTL)).toHaveValue(32);
      await fill(user, input(US), "");
      expect(input(INTL)).toHaveValue(32);
    });

    it("does not fill when a level has three nodes", async () => {
      const { user } = renderForm();
      await fill(user, input(US), "10");
      expect(input(INTL)).toHaveValue(32);
      expect(input(BONDS)).toHaveValue(20);
    });
  });

  describe("nested config", () => {
    it("nests children under their parent with '% of <parent>' labels", () => {
      renderForm(nestedConfig);
      const stocks = screen.getByRole("group", { name: "Stocks" });
      expect(within(stocks).getByLabelText(US_IN)).toHaveValue(70);
      expect(within(stocks).getByLabelText(INTL_IN)).toHaveValue(30);
      expect(within(stocks).queryByLabelText(BONDS_TOP)).toBeNull();
      expect(input(STOCKS)).toHaveValue(60);
      expect(input(BONDS_TOP)).toHaveValue(40);
    });

    it("shows whole-portfolio readouts on nested nodes only", () => {
      renderForm(nestedConfig);
      expect(readout("42.0%")).toBeInTheDocument();
      expect(readout("18.0%")).toBeInTheDocument();
      expect(readout("60.0%")).toBeNull(); // Stocks is top level
      expect(readout("40.0%")).toBeNull(); // Bonds is top level
    });

    it("pair-fills Bonds when Stocks is typed and updates the readouts", async () => {
      const { user } = renderForm(blankNested);
      await fill(user, input(STOCKS), "60");
      expect(input(BONDS_TOP)).toHaveValue(40);
      expect(readout("42.0%")).toBeInTheDocument();
      expect(readout("18.0%")).toBeInTheDocument();
    });

    it("pair-fills within a nested level without touching the top level", async () => {
      const { user } = renderForm(nestedConfig);
      await fill(user, input(US_IN), "80");
      expect(input(INTL_IN)).toHaveValue(20);
      expect(input(STOCKS)).toHaveValue(60);
      expect(input(BONDS_TOP)).toHaveValue(40);
    });

    it("re-labels a category moved to the top level and keeps other edits", async () => {
      const { user, rerender } = renderForm(nestedConfig);
      await fill(user, input(BONDS_TOP), "30");
      const moved: ConfigSummary = {
        ...nestedConfig,
        categories: nestedConfig.categories.map((c) =>
          c.name === "International" ? { ...c, parent: null } : c,
        ),
      };
      await rerender({ config: moved });
      expect(input(INTL)).toHaveValue(30); // now "% of portfolio"
      expect(screen.queryByLabelText(INTL_IN)).toBeNull();
      expect(input(BONDS_TOP)).toHaveValue(30);
    });
  });

  describe("level errors", () => {
    it("shows a nested level's message beside that level only, with aria wiring", async () => {
      const { user } = renderForm(nestedConfig);
      await fill(user, input(INTL_IN), "");
      const stocks = screen.getByRole("group", { name: "Stocks" });
      const message = within(stocks).getByText("Stocks: must add up to 100% (currently 70.0%).");
      expect(message).toHaveClass("sum-indicator", "err");
      expect(message).not.toHaveAttribute("role", "alert");
      for (const label of [US_IN, INTL_IN]) {
        expect(input(label)).toHaveAttribute("aria-invalid", "true");
        expect(input(label)).toHaveAccessibleDescription(message.textContent!);
      }
      expect(input(STOCKS)).not.toHaveAttribute("aria-invalid");
      expect(screen.queryByText(/^Top level/)).toBeNull();
    });

    it("shows a top-level message for the top level", async () => {
      const { user } = renderForm(nestedConfig);
      await fill(user, input(BONDS_TOP), "");
      expect(screen.getByText("Top level: must add up to 100% (currently 60.0%).")).toBeVisible();
      expect(input(STOCKS)).toHaveAttribute("aria-invalid", "true");
      expect(input(BONDS_TOP)).toHaveAttribute("aria-invalid", "true");
      expect(input(US_IN)).not.toHaveAttribute("aria-invalid");
    });

    it("reports an out-of-range share instead of the total", async () => {
      const { user } = renderForm(nestedConfig);
      await fill(user, input(US_IN), "150");
      expect(
        screen.getByText("Stocks: each share must be between 0% and 100%."),
      ).toBeInTheDocument();
    });

    it("clears the message once the level adds up again", async () => {
      const { user, levelErrors } = renderForm();
      await fill(user, input(BONDS), "15");
      expect(levelErrors()).toHaveLength(1);
      await fill(user, input(BONDS), "20");
      expect(levelErrors()).toHaveLength(0);
      expect(input(BONDS)).not.toHaveAttribute("aria-invalid");
    });
  });

  describe("edits and config changes", () => {
    it("keeps edits across a re-render with a new config object", async () => {
      const { user, rerender } = renderForm();
      await fill(user, input(BONDS), "30");
      await rerender({ config: structuredClone(config) });
      expect(input(BONDS)).toHaveValue(30);
      await rerender({ allocation: { ...allocation } });
      expect(input(BONDS)).toHaveValue(30);
    });

    it("adds an input with its default for a new category without touching edits", async () => {
      const { user, rerender } = renderForm();
      await fill(user, input(BONDS), "30");
      const added: Category = {
        name: "Gold",
        buy_symbol: "GLD",
        parent: null,
        target: 5,
        color: "#eda100",
      };
      await rerender({ config: { ...config, categories: [...config.categories, added] } });
      expect(input("Gold % of portfolio")).toHaveValue(5);
      expect(input(BONDS)).toHaveValue(30);
      expect(input(US)).toHaveValue(48);
    });

    it("shows a new childless category without a target as an empty input", async () => {
      const { rerender, levelErrors } = renderForm();
      const added: Category = {
        name: "Gold",
        buy_symbol: null,
        parent: null,
        target: null,
        color: "#eda100",
      };
      await rerender({ config: { ...config, categories: [...config.categories, added] } });
      expect(input("Gold % of portfolio")).toHaveValue(null);
      expect(levelErrors()).toHaveLength(0);
    });

    it("drops the input of a removed category and re-checks the level", async () => {
      const { rerender } = renderForm();
      await rerender({ config: twoFlat });
      expect(screen.queryByLabelText(BONDS)).toBeNull();
      expect(screen.getByText("Top level: must add up to 100% (currently 80.0%).")).toBeVisible();
    });

    it("follows a changed default for rows the user has not edited", async () => {
      const { user, rerender } = renderForm();
      await fill(user, input(US), "10");
      await rerender({
        config: { ...config, categories: config.categories.map((c) => ({ ...c, target: 25 })) },
      });
      expect(input(INTL)).toHaveValue(25);
      expect(input(US)).toHaveValue(10);
    });
  });

  describe("empty tree", () => {
    it("shows a hint and no submit button when there are no categories", () => {
      render(RebalanceForm, {
        props: { allocation, config: { ...config, categories: [] }, onResult: vi.fn() },
      });
      expect(screen.getByText("Add a category to set targets.")).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: BUTTON })).toBeNull();
    });
  });

  describe("validation", () => {
    it.each([
      ["empty", ""],
      ["zero", "0"],
      ["negative", "-5"],
    ])("rejects a %s investment amount", async (_name, value) => {
      const { user, amount } = renderForm();
      await fill(user, amount, value);
      await submit(user);
      expect(screen.getByRole("alert")).toHaveTextContent(AMOUNT_MESSAGE);
      expect(mockFetch).not.toHaveBeenCalled();
    });

    it.each([
      ["negative", "-1"],
      ["above 100", "101"],
    ])("rejects a %s share", async (_name, value) => {
      const { user, amount } = renderForm();
      await fill(user, amount, "5000");
      await fill(user, input(BONDS), value);
      await submit(user);
      expect(screen.getByRole("alert")).toHaveTextContent(RANGE_MESSAGE);
      expect(mockFetch).not.toHaveBeenCalled();
    });

    it("reports the amount problem before share problems", async () => {
      const { user } = renderForm();
      await fill(user, input(BONDS), "150");
      await submit(user);
      expect(screen.getByRole("alert")).toHaveTextContent(AMOUNT_MESSAGE);
    });

    it("never calls onResult for an invalid submit", async () => {
      const { user, onResult } = renderForm();
      await submit(user);
      expect(onResult).not.toHaveBeenCalled();
    });
  });

  describe("submitting", () => {
    it("fetches with the category targets and passes the result on", async () => {
      mockFetch.mockResolvedValue(rebalance);
      const { user, amount, onResult } = renderForm();
      await fill(user, amount, "5000");
      await submit(user);

      await waitFor(() => expect(onResult).toHaveBeenCalledTimes(1));
      expect(onResult).toHaveBeenCalledWith(rebalance);
      expect(mockFetch).toHaveBeenCalledTimes(1);
      const [passedAllocation, request] = mockFetch.mock.calls[0];
      expect(passedAllocation).toBe(allocation);
      expect(request).toEqual({
        investment_amount: 5000,
        target: { "US Stocks": 48, International: 32, Bonds: 20 },
      });
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    });

    it("sends an emptied input as 0", async () => {
      mockFetch.mockResolvedValue(rebalance);
      const { user, amount, onResult } = renderForm();
      await fill(user, amount, "5000");
      await fill(user, input(BONDS), "");
      await fill(user, input(INTL), "52");
      await submit(user);

      await waitFor(() => expect(onResult).toHaveBeenCalled());
      expect(mockFetch.mock.calls[0][1].target).toEqual({
        "US Stocks": 48,
        International: 52,
        Bonds: 0,
      });
    });

    it("sends whole-portfolio targets for leaves only when nested", async () => {
      mockFetch.mockResolvedValue(rebalance);
      const { user, amount, onResult } = renderForm(nestedConfig);
      await fill(user, amount, "5000");
      await submit(user);

      await waitFor(() => expect(onResult).toHaveBeenCalled());
      const [passedAllocation, request] = mockFetch.mock.calls[0];
      expect(passedAllocation).toBe(allocation);
      expect(request.investment_amount).toBe(5000);
      expect(Object.keys(request.target).sort()).toEqual(["Bonds", "International", "US Stocks"]); // no "Stocks"
      expect(request.target["US Stocks"]).toBeCloseTo(42);
      expect(request.target.International).toBeCloseTo(18);
      expect(request.target.Bonds).toBeCloseTo(40);
    });

    it("uses edited nested shares in the request", async () => {
      mockFetch.mockResolvedValue(rebalance);
      const { user, amount, onResult } = renderForm(blankNested);
      await fill(user, amount, "100");
      await fill(user, input(STOCKS), "50"); // fills Bonds 50
      await fill(user, input(US_IN), "80"); // fills International 20
      await submit(user);

      await waitFor(() => expect(onResult).toHaveBeenCalled());
      const { target } = mockFetch.mock.calls[0][1];
      expect(target["US Stocks"]).toBeCloseTo(40);
      expect(target.International).toBeCloseTo(10);
      expect(target.Bonds).toBeCloseTo(50);
    });

    it("shows a calculating state while the request is pending", async () => {
      const { promise, resolve } = Promise.withResolvers<RebalanceResult>();
      mockFetch.mockReturnValue(promise);
      const { user, amount } = renderForm();
      await fill(user, amount, "5000");
      await submit(user);

      const button = await screen.findByRole("button", { name: "Calculating…" });
      expect(button).toBeDisabled();

      resolve(rebalance);
      const idle = await screen.findByRole("button", { name: BUTTON });
      expect(idle).toBeEnabled();
    });

    it("displays the API error message and does not call onResult", async () => {
      mockFetch.mockRejectedValue(new Error("Server exploded"));
      const { user, amount, onResult } = renderForm();
      await fill(user, amount, "5000");
      await submit(user);

      expect(await screen.findByRole("alert")).toHaveTextContent("Server exploded");
      expect(onResult).not.toHaveBeenCalled();
      expect(screen.getByRole("button", { name: BUTTON })).toBeEnabled();
    });

    it("clears a previous error when the next submit succeeds", async () => {
      mockFetch.mockRejectedValueOnce(new Error("Server exploded"));
      mockFetch.mockResolvedValueOnce(rebalance);
      const { user, amount, onResult } = renderForm();
      await fill(user, amount, "5000");
      await submit(user);
      expect(await screen.findByRole("alert")).toBeInTheDocument();

      await submit(user);
      await waitFor(() => expect(onResult).toHaveBeenCalledWith(rebalance));
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    });
  });
});
