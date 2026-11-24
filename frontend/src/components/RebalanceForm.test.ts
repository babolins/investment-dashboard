import { render, screen, waitFor } from "@testing-library/svelte";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fetchRebalance } from "../services/api";
import { allocation, config, rebalance } from "../test/fixtures";
import type { Category, RebalanceResult } from "../types";
import RebalanceForm from "./RebalanceForm.svelte";

vi.mock("../services/api", () => ({ fetchRebalance: vi.fn() }));
const mockFetch = vi.mocked(fetchRebalance);

const BUTTON = "Calculate Buy Guidance";
const AMOUNT_MESSAGE = "Enter a positive investment amount.";
const RANGE_MESSAGE = "Each target must be between 0% and 100%.";

const US = "US Stocks (VTI)";
const INTL = "International (VXUS)";
const BONDS = "Bonds (BND)";

function renderForm(categories: Category[] = config.categories) {
  const onResult = vi.fn();
  const view = render(RebalanceForm, { props: { allocation, categories, onResult } });
  return {
    ...view,
    onResult,
    user: userEvent.setup(),
    amount: screen.getByLabelText("Investment Amount ($)"),
    indicator: () => view.container.querySelector(".sum-indicator"),
  };
}

type Form = ReturnType<typeof renderForm>;

async function fill(user: Form["user"], input: HTMLElement, value: string) {
  await user.clear(input);
  if (value) await user.type(input, value);
}

const submit = (user: Form["user"]) => user.click(screen.getByRole("button", { name: BUTTON }));
const input = (label: string) => screen.getByLabelText(label);

beforeEach(() => vi.resetAllMocks());

describe("RebalanceForm", () => {
  it("renders the heading, amount input and one labelled input per category", () => {
    const { amount } = renderForm();
    expect(screen.getByRole("heading", { name: "Rebalance Calculator" })).toBeInTheDocument();
    expect(screen.getByText("Targets (%)")).toBeInTheDocument();
    expect(amount).toHaveValue(null);
    expect(screen.getByRole("button", { name: BUTTON })).toBeEnabled();
    expect(screen.getAllByRole("spinbutton")).toHaveLength(4); // amount + 3 categories
    for (const label of [US, INTL, BONDS]) expect(input(label)).toBeInTheDocument();
  });

  describe("prefill", () => {
    it("fills each input from the category target", () => {
      const { indicator } = renderForm();
      expect(input(US)).toHaveValue(48);
      expect(input(INTL)).toHaveValue(32);
      expect(input(BONDS)).toHaveValue(20);
      expect(indicator()).toHaveTextContent("Total: 100.0%");
      expect(indicator()).toHaveClass("ok");
    });

    it("leaves inputs empty for categories without a target", () => {
      const { indicator } = renderForm(config.categories.map((c) => ({ ...c, target: null })));
      expect(input(US)).toHaveValue(null);
      expect(input(BONDS)).toHaveValue(null);
      expect(indicator()).toHaveTextContent("Total: 0.0%");
      expect(indicator()).toHaveClass("err");
    });

    it("shows inputs when the categories arrive after mount", async () => {
      const { rerender, indicator } = renderForm([]);
      expect(screen.queryByLabelText(US)).toBeNull();
      await rerender({ categories: config.categories });
      expect(input(US)).toHaveValue(48);
      expect(input(BONDS)).toHaveValue(20);
      expect(indicator()).toHaveClass("ok");
    });

    it("keeps edits across a re-render with a new categories array", async () => {
      const { user, rerender } = renderForm();
      await fill(user, input(BONDS), "30");
      await rerender({ categories: config.categories.map((c) => ({ ...c })) });
      expect(input(BONDS)).toHaveValue(30);
      await rerender({ allocation: { ...allocation } });
      expect(input(BONDS)).toHaveValue(30);
    });

    it("adds an input with its default for a new category without touching edits", async () => {
      const { user, rerender } = renderForm();
      await fill(user, input(BONDS), "30");
      const added: Category = { name: "Gold", buy_symbol: "GLD", target: 5, color: "#eda100" };
      await rerender({ categories: [...config.categories, added] });
      expect(input("Gold (GLD)")).toHaveValue(5);
      expect(input(BONDS)).toHaveValue(30);
      expect(input(US)).toHaveValue(48);
    });

    it("gives a new category without a target an empty input", async () => {
      const { rerender } = renderForm();
      const added: Category = { name: "Gold", buy_symbol: "GLD", target: null, color: "#eda100" };
      await rerender({ categories: [...config.categories, added] });
      expect(input("Gold (GLD)")).toHaveValue(null);
    });

    it("drops the input of a removed category and excludes it from the total", async () => {
      const { rerender, indicator } = renderForm();
      await rerender({ categories: config.categories.slice(0, 2) });
      expect(screen.queryByLabelText(BONDS)).toBeNull();
      expect(indicator()).toHaveTextContent("Total: 80.0%");
      expect(indicator()).toHaveClass("err");
    });

    it("follows a changed default for rows the user has not edited", async () => {
      const { user, rerender } = renderForm();
      await fill(user, input(US), "10");
      await rerender({
        categories: config.categories.map((c) => ({ ...c, target: 25 })),
      });
      expect(input(INTL)).toHaveValue(25);
      expect(input(US)).toHaveValue(10);
    });
  });

  describe("total indicator", () => {
    it("updates live as the inputs are edited", async () => {
      const { user, indicator } = renderForm();
      await fill(user, input(US), "30");
      await fill(user, input(INTL), "50");
      expect(indicator()).toHaveTextContent("Total: 100.0%");
      expect(indicator()).toHaveClass("ok");
      expect(indicator()).not.toHaveClass("err");
    });

    it("turns into an error state when the total is off or an input is out of range", async () => {
      const { user, indicator } = renderForm();
      await fill(user, input(US), "40");
      expect(indicator()).toHaveTextContent("Total: 92.0%");
      expect(indicator()).toHaveClass("err");
      expect(indicator()).not.toHaveClass("ok");
      await fill(user, input(US), "150");
      expect(indicator()).toHaveClass("err");
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
    ])("rejects a %s target", async (_name, value) => {
      const { user, amount } = renderForm();
      await fill(user, amount, "5000");
      await fill(user, input(BONDS), value);
      await submit(user);
      expect(screen.getByRole("alert")).toHaveTextContent(RANGE_MESSAGE);
      expect(mockFetch).not.toHaveBeenCalled();
    });

    it("rejects targets that do not add up to 100%", async () => {
      const { user, amount } = renderForm();
      await fill(user, amount, "5000");
      await fill(user, input(BONDS), "15");
      await submit(user);
      expect(screen.getByRole("alert")).toHaveTextContent(
        "Targets must add up to 100% (currently 95.0%).",
      );
      expect(mockFetch).not.toHaveBeenCalled();
    });

    it("reports the amount problem before target problems", async () => {
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

    it("uses edited target values in the request", async () => {
      mockFetch.mockResolvedValue(rebalance);
      const { user, amount, onResult } = renderForm();
      await fill(user, amount, "250.5");
      await fill(user, input(US), "30");
      await fill(user, input(INTL), "50");
      await submit(user);

      await waitFor(() => expect(onResult).toHaveBeenCalled());
      expect(mockFetch.mock.calls[0][1]).toEqual({
        investment_amount: 250.5,
        target: { "US Stocks": 30, International: 50, Bonds: 20 },
      });
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

    it("omits a removed category from the request", async () => {
      mockFetch.mockResolvedValue(rebalance);
      const { user, amount, rerender, onResult } = renderForm();
      await rerender({ categories: config.categories.slice(0, 2) });
      await fill(user, amount, "5000");
      await fill(user, input(INTL), "52");
      await submit(user);

      await waitFor(() => expect(onResult).toHaveBeenCalled());
      expect(mockFetch.mock.calls[0][1].target).toEqual({ "US Stocks": 48, International: 52 });
    });

    it("shows a calculating state while the request is pending", async () => {
      let resolve!: (result: RebalanceResult) => void;
      mockFetch.mockReturnValue(new Promise((r) => (resolve = r)));
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

    it("shows a generic message when a non-Error is thrown", async () => {
      mockFetch.mockRejectedValue("boom");
      const { user, amount } = renderForm();
      await fill(user, amount, "5000");
      await submit(user);
      expect(await screen.findByRole("alert")).toHaveTextContent("Unknown error");
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
