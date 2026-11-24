import { render, screen, waitFor } from "@testing-library/svelte";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fetchRebalance } from "../services/api";
import { allocation, config, rebalance } from "../test/fixtures";
import type { RebalanceResult, TargetAllocation } from "../types";
import RebalanceForm from "./RebalanceForm.svelte";

vi.mock("../services/api", () => ({ fetchRebalance: vi.fn() }));
const mockFetch = vi.mocked(fetchRebalance);

const BUTTON = "Calculate Buy Guidance";
const BND_MESSAGE = "BND target must be between 0% and 100%.";
const VXUS_MESSAGE = "VXUS (of stocks) target must be between 0% and 100%.";
const AMOUNT_MESSAGE = "Enter a positive investment amount.";

function renderForm(defaultTarget: TargetAllocation | null = config.default_target) {
  const onResult = vi.fn();
  const view = render(RebalanceForm, { props: { allocation, defaultTarget, onResult } });
  return {
    ...view,
    onResult,
    user: userEvent.setup(),
    amount: screen.getByLabelText("Investment Amount ($)"),
    bnd: screen.getByLabelText("BND (of total portfolio)"),
    vxus: screen.getByLabelText("VXUS (of stocks only)"),
    indicator: () => view.container.querySelector(".sum-indicator"),
  };
}

type Form = ReturnType<typeof renderForm>;

async function fill(user: Form["user"], input: HTMLElement, value: string) {
  await user.clear(input);
  if (value) await user.type(input, value);
}

const submit = (user: Form["user"]) => user.click(screen.getByRole("button", { name: BUTTON }));

beforeEach(() => vi.resetAllMocks());

describe("RebalanceForm", () => {
  it("renders the heading, hint and labelled inputs", () => {
    const { amount } = renderForm();
    expect(screen.getByRole("heading", { name: "Rebalance Calculator" })).toBeInTheDocument();
    expect(
      screen.getByText("Enter BND as a whole-portfolio target, then VXUS as a share of stocks."),
    ).toBeInTheDocument();
    expect(screen.getByText("Inputs (%)")).toBeInTheDocument();
    expect(amount).toHaveValue(null);
    expect(screen.getByRole("button", { name: BUTTON })).toBeEnabled();
  });

  describe("prefill", () => {
    it("fills BND and VXUS-of-stocks from the default target", async () => {
      const { bnd, vxus, indicator } = renderForm({ vti: 48, vxus: 32, bnd: 20 });
      await waitFor(() => expect(bnd).toHaveValue(20));
      expect(vxus).toHaveValue(40);
      expect(indicator()).toHaveTextContent("Derived Targets: VTI 48.0% · VXUS 32.0% · BND 20.0%");
      expect(indicator()).toHaveClass("ok");
    });

    it("leaves inputs empty and flags an error without a default target", () => {
      const { bnd, vxus, indicator } = renderForm(null);
      expect(bnd).toHaveValue(null);
      expect(vxus).toHaveValue(null);
      expect(indicator()).toHaveTextContent("Derived Targets: VTI 0.0% · VXUS 0.0% · BND 0.0%");
      expect(indicator()).toHaveClass("err");
    });

    it("fills the inputs when the default target arrives after mount", async () => {
      const { bnd, vxus, rerender } = renderForm(null);
      await rerender({ defaultTarget: { vti: 48, vxus: 32, bnd: 20 } });
      await waitFor(() => expect(bnd).toHaveValue(20));
      expect(vxus).toHaveValue(40);
    });

    it("overwrites the inputs when the default target changes", async () => {
      const { bnd, vxus, rerender } = renderForm();
      await waitFor(() => expect(bnd).toHaveValue(20));
      await rerender({ defaultTarget: { vti: 30, vxus: 30, bnd: 40 } });
      await waitFor(() => expect(bnd).toHaveValue(40));
      expect(vxus).toHaveValue(50);
    });

    it("does not clobber user edits on an unrelated re-render", async () => {
      const { user, bnd, rerender } = renderForm();
      await waitFor(() => expect(bnd).toHaveValue(20));
      await fill(user, bnd, "30");
      await rerender({ allocation: { ...allocation } });
      expect(bnd).toHaveValue(30);
    });

    it("keeps the inputs when the default target goes back to null", async () => {
      const { bnd, rerender } = renderForm();
      await waitFor(() => expect(bnd).toHaveValue(20));
      await rerender({ defaultTarget: null });
      expect(bnd).toHaveValue(20);
    });
  });

  describe("derived targets indicator", () => {
    it("updates live as the inputs are edited", async () => {
      const { user, bnd, vxus, indicator } = renderForm();
      await waitFor(() => expect(bnd).toHaveValue(20));
      await fill(user, bnd, "30");
      await fill(user, vxus, "50");
      expect(indicator()).toHaveTextContent("Derived Targets: VTI 35.0% · VXUS 35.0% · BND 30.0%");
      expect(indicator()).toHaveClass("ok");
      expect(indicator()).not.toHaveClass("err");
    });

    it("turns into an error state when an input is out of range", async () => {
      const { user, bnd, indicator } = renderForm();
      await waitFor(() => expect(bnd).toHaveValue(20));
      await fill(user, bnd, "150");
      expect(indicator()).toHaveClass("err");
      expect(indicator()).not.toHaveClass("ok");
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
      ["empty", ""],
      ["negative", "-1"],
      ["above 100", "101"],
    ])("rejects a %s BND target", async (_name, value) => {
      const { user, amount, bnd } = renderForm();
      await fill(user, amount, "5000");
      await fill(user, bnd, value);
      await submit(user);
      expect(screen.getByRole("alert")).toHaveTextContent(BND_MESSAGE);
      expect(mockFetch).not.toHaveBeenCalled();
    });

    it.each([
      ["empty", ""],
      ["negative", "-1"],
      ["above 100", "101"],
    ])("rejects a %s VXUS target", async (_name, value) => {
      const { user, amount, vxus } = renderForm();
      await fill(user, amount, "5000");
      await fill(user, vxus, value);
      await submit(user);
      expect(screen.getByRole("alert")).toHaveTextContent(VXUS_MESSAGE);
      expect(mockFetch).not.toHaveBeenCalled();
    });

    it("reports the BND problem first when both targets are invalid", async () => {
      const { user, amount, bnd, vxus } = renderForm();
      await fill(user, amount, "5000");
      await fill(user, bnd, "150");
      await fill(user, vxus, "150");
      await submit(user);
      expect(screen.getByRole("alert")).toHaveTextContent(BND_MESSAGE);
    });

    it("reports the amount problem before target problems", async () => {
      const { user, bnd } = renderForm();
      await fill(user, bnd, "150");
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
    it("fetches with the derived targets and passes the result on", async () => {
      mockFetch.mockResolvedValue(rebalance);
      const { user, amount, onResult, bnd } = renderForm();
      await waitFor(() => expect(bnd).toHaveValue(20));
      await fill(user, amount, "5000");
      await submit(user);

      await waitFor(() => expect(onResult).toHaveBeenCalledTimes(1));
      expect(onResult).toHaveBeenCalledWith(rebalance);
      expect(mockFetch).toHaveBeenCalledTimes(1);
      const [passedAllocation, request] = mockFetch.mock.calls[0];
      expect(passedAllocation).toBe(allocation);
      expect(request.investment_amount).toBe(5000);
      expect(request.target.vti).toBeCloseTo(48);
      expect(request.target.vxus).toBeCloseTo(32);
      expect(request.target.bnd).toBeCloseTo(20);
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    });

    it("uses edited target values in the request", async () => {
      mockFetch.mockResolvedValue(rebalance);
      const { user, amount, bnd, vxus, onResult } = renderForm();
      await waitFor(() => expect(bnd).toHaveValue(20));
      await fill(user, amount, "250.5");
      await fill(user, bnd, "30");
      await fill(user, vxus, "50");
      await submit(user);

      await waitFor(() => expect(onResult).toHaveBeenCalled());
      const request = mockFetch.mock.calls[0][1];
      expect(request.investment_amount).toBe(250.5);
      expect(request.target.vti).toBeCloseTo(35);
      expect(request.target.vxus).toBeCloseTo(35);
      expect(request.target.bnd).toBeCloseTo(30);
    });

    it("shows a calculating state while the request is pending", async () => {
      let resolve!: (result: RebalanceResult) => void;
      mockFetch.mockReturnValue(new Promise((r) => (resolve = r)));
      const { user, amount, bnd } = renderForm();
      await waitFor(() => expect(bnd).toHaveValue(20));
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
      const { user, amount, bnd, onResult } = renderForm();
      await waitFor(() => expect(bnd).toHaveValue(20));
      await fill(user, amount, "5000");
      await submit(user);

      expect(await screen.findByRole("alert")).toHaveTextContent("Server exploded");
      expect(onResult).not.toHaveBeenCalled();
      expect(screen.getByRole("button", { name: BUTTON })).toBeEnabled();
    });

    it("shows a generic message when a non-Error is thrown", async () => {
      mockFetch.mockRejectedValue("boom");
      const { user, amount, bnd } = renderForm();
      await waitFor(() => expect(bnd).toHaveValue(20));
      await fill(user, amount, "5000");
      await submit(user);
      expect(await screen.findByRole("alert")).toHaveTextContent("Unknown error");
    });

    it("clears a previous error when the next submit succeeds", async () => {
      mockFetch.mockRejectedValueOnce(new Error("Server exploded"));
      mockFetch.mockResolvedValueOnce(rebalance);
      const { user, amount, bnd, onResult } = renderForm();
      await waitFor(() => expect(bnd).toHaveValue(20));
      await fill(user, amount, "5000");
      await submit(user);
      expect(await screen.findByRole("alert")).toBeInTheDocument();

      await submit(user);
      await waitFor(() => expect(onResult).toHaveBeenCalledWith(rebalance));
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    });
  });
});
