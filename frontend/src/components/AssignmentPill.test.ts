import { render, screen, waitFor } from "@testing-library/svelte";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AssignmentPill from "./AssignmentPill.svelte";
import { setAssignment } from "../services/api";
import { config, nestedConfig } from "../test/fixtures";
import type { ConfigSummary } from "../types";

vi.mock("../services/api", () => ({ setAssignment: vi.fn() }));

// What the server would return after a save; the component must pass this through untouched.
const updated: ConfigSummary = { ...config, exclusions: [...config.exclusions, "NEW"] };

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(setAssignment).mockResolvedValue(updated);
});

function setup(symbol: string) {
  const onChange = vi.fn();
  render(AssignmentPill, { props: { symbol, config, onChange } });
  return { onChange, user: userEvent.setup(), pill: screen.getByRole("button") };
}

const checkbox = (name: string) => screen.getByRole("checkbox", { name });
const percents = () =>
  screen.queryAllByRole("spinbutton").map((i) => (i as HTMLInputElement).value);
const save = () => screen.getByRole("button", { name: "Save" });

describe("AssignmentPill label", () => {
  it.each([
    ["VTI", "US Stocks"],
    ["FZROX", "US Stocks 70% · International 30%"],
    ["SPAXX", "Excluded"],
    ["NEW", "Unassigned"],
  ])("shows %s as %s", (symbol, label) => {
    setup(symbol);
    expect(screen.getByRole("button")).toHaveTextContent(label);
  });

  it("starts collapsed", () => {
    const { pill } = setup("VTI");
    expect(pill).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("checkbox")).toBeNull();
  });
});

describe("AssignmentPill editor", () => {
  it("opens an editor reflecting the current assignment", async () => {
    const { user, pill } = setup("VTI");
    await user.click(pill);

    expect(pill).toHaveAttribute("aria-expanded", "true");
    expect(checkbox("US Stocks")).toBeChecked();
    expect(checkbox("International")).not.toBeChecked();
    expect(checkbox("Bonds")).not.toBeChecked();
    expect(checkbox("Exclude from allocation")).not.toBeChecked();
    expect(screen.queryAllByRole("spinbutton")).toHaveLength(0);
  });

  it("moves focus into the editor when it opens", async () => {
    const { user, pill } = setup("VTI");
    await user.click(pill);
    await waitFor(() => expect(checkbox("US Stocks")).toHaveFocus());
  });

  it("pre-fills an existing split", async () => {
    const { user, pill } = setup("FZROX");
    await user.click(pill);
    expect(checkbox("US Stocks")).toBeChecked();
    expect(checkbox("International")).toBeChecked();
    expect(percents()).toEqual(["70", "30"]);
  });

  it("shows Exclude ticked for an excluded symbol", async () => {
    const { user, pill } = setup("SPAXX");
    await user.click(pill);
    expect(checkbox("Exclude from allocation")).toBeChecked();
    expect(checkbox("US Stocks")).not.toBeChecked();
  });

  it("shows no percent input for a single selection, then splits evenly for two", async () => {
    const { user, pill } = setup("NEW");
    await user.click(pill);
    await user.click(checkbox("US Stocks"));
    expect(percents()).toEqual([]);

    await user.click(checkbox("International"));
    expect(percents()).toEqual(["50", "50"]);
  });

  it("re-splits evenly on every selection change, discarding manual edits", async () => {
    const { user, pill } = setup("NEW");
    await user.click(pill);
    await user.click(checkbox("US Stocks"));
    await user.click(checkbox("International"));
    await user.clear(screen.getAllByRole("spinbutton")[0]);
    await user.type(screen.getAllByRole("spinbutton")[0], "80");

    await user.click(checkbox("Bonds"));
    expect(percents()).toEqual(["33.33", "33.33", "33.34"]);

    await user.click(checkbox("Bonds"));
    expect(percents()).toEqual(["50", "50"]);
  });

  it("hides the percent inputs again when back to one category", async () => {
    const { user, pill } = setup("FZROX");
    await user.click(pill);
    await user.click(checkbox("International"));
    expect(percents()).toEqual([]);
  });

  it("makes Exclude and categories mutually exclusive", async () => {
    const { user, pill } = setup("FZROX");
    await user.click(pill);

    await user.click(checkbox("Exclude from allocation"));
    expect(checkbox("Exclude from allocation")).toBeChecked();
    expect(checkbox("US Stocks")).not.toBeChecked();
    expect(checkbox("International")).not.toBeChecked();
    expect(percents()).toEqual([]);

    await user.click(checkbox("Bonds"));
    expect(checkbox("Exclude from allocation")).not.toBeChecked();
    expect(checkbox("Bonds")).toBeChecked();
  });

  it("disables Save until the percentages total 100", async () => {
    const { user, pill } = setup("NEW");
    await user.click(pill);
    await user.click(checkbox("US Stocks"));
    await user.click(checkbox("International"));
    expect(save()).toBeEnabled();

    await user.clear(screen.getAllByRole("spinbutton")[0]);
    await user.type(screen.getAllByRole("spinbutton")[0], "70");
    expect(save()).toBeDisabled();

    await user.clear(screen.getAllByRole("spinbutton")[1]);
    await user.type(screen.getAllByRole("spinbutton")[1], "30");
    expect(save()).toBeEnabled();
  });

  it("disables Save when a percentage is blank", async () => {
    const { user, pill } = setup("FZROX");
    await user.click(pill);
    await user.clear(screen.getAllByRole("spinbutton")[0]);
    expect(save()).toBeDisabled();
  });
});

describe("AssignmentPill saving", () => {
  it("saves a single category as full weight and reports the server's config", async () => {
    const { user, pill, onChange } = setup("NEW");
    await user.click(pill);
    await user.click(checkbox("US Stocks"));
    await user.click(save());

    expect(setAssignment).toHaveBeenCalledWith("NEW", { weights: { "US Stocks": 1 } });
    await waitFor(() => expect(onChange).toHaveBeenCalledTimes(1));
    expect(onChange).toHaveBeenCalledWith(updated);
    expect(screen.queryByRole("checkbox")).toBeNull();
    expect(pill).toHaveAttribute("aria-expanded", "false");
    expect(pill).toHaveFocus();
  });

  it("saves a split as normalised fractions", async () => {
    const { user, pill } = setup("NEW");
    await user.click(pill);
    await user.click(checkbox("US Stocks"));
    await user.click(checkbox("Bonds"));
    await user.clear(screen.getAllByRole("spinbutton")[0]);
    await user.type(screen.getAllByRole("spinbutton")[0], "60");
    await user.clear(screen.getAllByRole("spinbutton")[1]);
    await user.type(screen.getAllByRole("spinbutton")[1], "40");
    await user.click(save());

    expect(setAssignment).toHaveBeenCalledWith("NEW", {
      weights: { "US Stocks": 0.6, Bonds: 0.4 },
    });
  });

  it("saves Exclude as { excluded: true }", async () => {
    const { user, pill } = setup("VTI");
    await user.click(pill);
    await user.click(checkbox("Exclude from allocation"));
    await user.click(save());

    expect(setAssignment).toHaveBeenCalledWith("VTI", { excluded: true });
  });

  it("unassigns when nothing is selected", async () => {
    const { user, pill, onChange } = setup("VTI");
    await user.click(pill);
    await user.click(checkbox("US Stocks"));
    await user.click(save());

    expect(setAssignment).toHaveBeenCalledWith("VTI", { weights: {} });
    await waitFor(() => expect(onChange).toHaveBeenCalledWith(updated));
  });

  it("disables the controls while saving and does not send twice", async () => {
    const { promise, resolve } = Promise.withResolvers<ConfigSummary>();
    vi.mocked(setAssignment).mockReturnValue(promise);
    const { user, pill, onChange } = setup("NEW");
    await user.click(pill);
    await user.click(checkbox("Bonds"));
    await user.click(save());

    const busy = screen.getByRole("button", { name: "Saving…" });
    expect(busy).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
    await user.click(busy);
    expect(setAssignment).toHaveBeenCalledTimes(1);

    resolve(updated);
    await waitFor(() => expect(onChange).toHaveBeenCalledWith(updated));
  });

  it("keeps the editor open and shows the server error inline", async () => {
    vi.mocked(setAssignment).mockRejectedValue(new Error("Could not save config: disk full"));
    const { user, pill, onChange } = setup("NEW");
    await user.click(pill);
    await user.click(checkbox("Bonds"));
    await user.click(save());

    expect(await screen.findByRole("alert")).toHaveTextContent("Could not save config: disk full");
    expect(onChange).not.toHaveBeenCalled();
    expect(pill).toHaveAttribute("aria-expanded", "true");
    expect(save()).toBeEnabled();
  });
});

describe("AssignmentPill cancelling", () => {
  it("closes on Cancel without saving, restoring the server state on reopen", async () => {
    const { user, pill, onChange } = setup("VTI");
    await user.click(pill);
    await user.click(checkbox("Bonds"));
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.queryByRole("checkbox")).toBeNull();
    expect(pill).toHaveFocus();
    expect(setAssignment).not.toHaveBeenCalled();
    expect(onChange).not.toHaveBeenCalled();

    await user.click(pill);
    expect(checkbox("Bonds")).not.toBeChecked();
    expect(checkbox("US Stocks")).toBeChecked();
  });

  it("closes on Escape and returns focus to the pill", async () => {
    const { user, pill, onChange } = setup("VTI");
    await user.click(pill);
    await user.click(checkbox("Bonds"));
    await user.keyboard("{Escape}");

    expect(screen.queryByRole("checkbox")).toBeNull();
    expect(pill).toHaveFocus();
    expect(pill).toHaveAttribute("aria-expanded", "false");
    expect(setAssignment).not.toHaveBeenCalled();
    expect(onChange).not.toHaveBeenCalled();
  });

  it("reflects a new config prop the next time it opens", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    const { rerender } = render(AssignmentPill, { props: { symbol: "VTI", config, onChange } });
    await rerender({
      symbol: "VTI",
      config: { ...config, assignments: { VTI: { Bonds: 1 } } },
      onChange,
    });

    const pill = screen.getByRole("button");
    expect(pill).toHaveTextContent("Bonds");
    await user.click(pill);
    expect(checkbox("Bonds")).toBeChecked();
    expect(checkbox("US Stocks")).not.toBeChecked();
  });
});

describe("AssignmentPill categories offered", () => {
  it("offers only leaf categories, not parents", async () => {
    const user = userEvent.setup();
    render(AssignmentPill, { props: { symbol: "VTI", config: nestedConfig, onChange: vi.fn() } });
    await user.click(screen.getByRole("button"));

    expect(screen.queryByRole("checkbox", { name: "Stocks" })).toBeNull();
    expect(screen.getByRole("checkbox", { name: "US Stocks" })).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Bonds" })).toBeInTheDocument();
  });
});
