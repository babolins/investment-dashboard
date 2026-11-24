import { fireEvent, render, screen, waitFor, within } from "@testing-library/svelte";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import CategoryManager from "./CategoryManager.svelte";
import { createCategory, deleteCategory, updateCategory } from "../services/api";
import { config } from "../test/fixtures";
import type { ConfigSummary } from "../types";

vi.mock("../services/api", () => ({
  createCategory: vi.fn(),
  updateCategory: vi.fn(),
  deleteCategory: vi.fn(),
}));

// What the server would return after a mutation; passed through untouched.
const updated: ConfigSummary = { ...config, exclusions: [] };

beforeEach(() => {
  vi.resetAllMocks();
  for (const fn of [createCategory, updateCategory, deleteCategory]) {
    vi.mocked(fn).mockResolvedValue(updated);
  }
});

const cat = (
  name: string,
  parent: string | null,
  target: number | null,
  buy_symbol: string | null = null,
) => ({ name, parent, target, buy_symbol, color: buy_symbol ? "#2a78d6" : null });

// Stocks (60) > Core (50) > US Stocks, Stocks > International (50); Bonds (40, holds BND);
// Spare (empty leaf). Bonds is the only leaf with securities assigned.
const nested: ConfigSummary = {
  categories: [
    cat("Stocks", null, 60),
    cat("Core", "Stocks", 50),
    cat("US Stocks", "Core", 100, "VTI"),
    cat("International", "Stocks", 50, "VXUS"),
    cat("Bonds", null, 40, "BND"),
    cat("Spare", null, null),
  ],
  assignments: { BND: { Bonds: 1 } },
  exclusions: [],
};

function setup(cfg: ConfigSummary = config) {
  const onChange = vi.fn();
  render(CategoryManager, { props: { config: cfg, onChange } });
  return { onChange, user: userEvent.setup() };
}

type User = ReturnType<typeof userEvent.setup>;

// Rows are role="group" divs (they exclude nested children, unlike their <li>).
const row = (name: string) => screen.getByRole("group", { name });
const rowItem = (name: string) => row(name).closest("li") as HTMLElement;
const topZone = () => screen.getByRole("group", { name: "Top level" });
const moveSelect = (name: string) => screen.getByLabelText(`Move ${name} to`);
const optionNames = (select: HTMLElement) =>
  within(select)
    .getAllByRole("option")
    .map((o) => o.textContent?.trim());

const dnd = {
  async drag(source: HTMLElement, target: HTMLElement) {
    await fireEvent.dragStart(source);
    await fireEvent.dragOver(target);
    await fireEvent.drop(target);
    await fireEvent.dragEnd(source);
  },
};

function withLeaves(count: number): ConfigSummary {
  return {
    ...config,
    categories: Array.from({ length: count }, (_, i) => cat(`Cat ${i}`, null, null, "VTI")),
  };
}

describe("CategoryManager list", () => {
  it("lists a flat config in order with buy symbol and default target", () => {
    setup();
    expect(screen.getByRole("heading", { name: "Categories" })).toBeInTheDocument();
    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(3);
    expect(items[0]).toHaveTextContent("US Stocks");
    expect(items[0]).toHaveTextContent("VTI");
    expect(items[0]).toHaveTextContent("48%");
    expect(items[1]).toHaveTextContent("International");
    expect(items[2]).toHaveTextContent("Bonds");
    expect(items[2]).toHaveTextContent("20%");
  });

  it("renders categories as a tree, children nested inside their parent in config order", () => {
    setup(nested);
    const names = screen.getAllByRole("group").map((g) => g.getAttribute("aria-label"));
    expect(names).toEqual([
      "Top level",
      "Stocks",
      "Core",
      "US Stocks",
      "International",
      "Bonds",
      "Spare",
    ]);

    expect(within(rowItem("Stocks")).getByRole("group", { name: "Core" })).toBeInTheDocument();
    expect(within(rowItem("Spare")).queryByRole("group", { name: "Bonds" })).toBeNull();
    // Nesting means each level sits in a deeper list.
    const depth = (name: string) => {
      let n = 0;
      for (let el = rowItem(name).parentElement; el; el = el.parentElement) {
        if (el.tagName === "UL") n++;
      }
      return n;
    };
    expect(depth("Stocks")).toBe(1);
    expect(depth("Core")).toBe(2);
    expect(depth("US Stocks")).toBe(3);
  });

  it("shows a sub-category count on parents and the buy symbol on leaves", () => {
    setup(nested);
    expect(row("Stocks")).toHaveTextContent("60%");
    expect(row("Stocks")).toHaveTextContent("2 sub-categories");
    expect(row("Core")).toHaveTextContent("1 sub-category");
    expect(row("US Stocks")).toHaveTextContent("VTI");
    expect(row("US Stocks")).not.toHaveTextContent(/sub-categor/);
    expect(row("Spare")).toHaveTextContent("—");
    expect(row("Spare")).not.toHaveTextContent(/sub-categor/);
  });

  it("confirms per level when default targets total 100%", () => {
    setup(nested);
    expect(screen.getByText(/top level targets total 100%/i)).toBeInTheDocument();
    expect(screen.getByText(/stocks targets total 100%/i)).toBeInTheDocument();
  });

  it("warns only for the level whose targets do not total 100%", () => {
    setup({
      ...nested,
      categories: nested.categories.map((c) =>
        c.name === "International" ? { ...c, target: 20 } : c,
      ),
    });
    expect(screen.getByText(/stocks targets total 70%/i)).toHaveTextContent(/not 100%/);
    expect(screen.getByText(/top level targets total 100%/i)).not.toHaveTextContent(/not 100%/);
  });

  it("hints at the leaf cap at 8 leaves, but does not disable adding", () => {
    const { unmount } = render(CategoryManager, {
      props: { config: withLeaves(7), onChange: vi.fn() },
    });
    expect(screen.queryByText(/maximum of 8/i)).toBeNull();
    unmount();

    render(CategoryManager, { props: { config: withLeaves(8), onChange: vi.fn() } });
    expect(screen.getByText(/maximum of 8 leaf categories/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add category" })).toBeEnabled();
  });
});

describe("CategoryManager add category", () => {
  const form = () => screen.getByRole("form", { name: "Add category" });
  const field = (label: string) => within(form()).getByLabelText(label);
  const submit = async (user: User) =>
    user.click(within(form()).getByRole("button", { name: "Add category" }));

  async function fill(user: User, name: string, symbol = "", target = "") {
    if (name) await user.type(field("Name"), name);
    if (symbol) await user.type(field("Buy symbol"), symbol);
    if (target) await user.type(field("Default % of parent"), target);
  }

  it("creates a top-level category, trimming and uppercasing, and reports the config", async () => {
    const { user, onChange } = setup(nested);
    await fill(user, "  Gold ", "gld", "5");
    await submit(user);

    expect(createCategory).toHaveBeenCalledWith({
      name: "Gold",
      buy_symbol: "GLD",
      target: 5,
      parent: null,
    });
    await waitFor(() => expect(onChange).toHaveBeenCalledWith(updated));
    expect(field("Name")).toHaveValue("");
    expect(field("Buy symbol")).toHaveValue("");
  });

  it("creates a category inside the chosen parent with a null symbol and target", async () => {
    const { user } = setup(nested);
    await fill(user, "Intl Small");
    await user.selectOptions(field("Inside"), "International");
    await submit(user);

    expect(createCategory).toHaveBeenCalledWith({
      name: "Intl Small",
      buy_symbol: null,
      target: null,
      parent: "International",
    });
  });

  it("offers Top level and every category except leaves holding securities", () => {
    setup(nested);
    expect(optionNames(field("Inside"))).toEqual([
      "Top level",
      "Stocks",
      "Core",
      "US Stocks",
      "International",
      "Spare",
    ]);
  });

  it.each([
    ["a blank name", "", "", "10"],
    ["a name containing a slash", "a/b", "", "10"],
    ["a reserved name", "Unassigned", "", "10"],
    ["a name already taken (any case)", "bonds", "", "10"],
    ["a target above 100", "Fine", "", "150"],
    ["an invalid buy symbol", "Fine", "not a symbol", "10"],
  ])("rejects %s without calling the API", async (_label, name, symbol, target) => {
    const { user } = setup(nested);
    await fill(user, name, symbol, target);
    await submit(user);

    expect(await within(form()).findByRole("alert")).toBeInTheDocument();
    expect(createCategory).not.toHaveBeenCalled();
  });

  it("shows a server error inline and keeps the form", async () => {
    const message = "Category 'Bonds' has securities assigned (BND); move them first.";
    vi.mocked(createCategory).mockRejectedValue(new Error(message));
    const { user, onChange } = setup(nested);
    await fill(user, "Gold");
    await submit(user);

    expect(await within(form()).findByRole("alert")).toHaveTextContent(message);
    expect(onChange).not.toHaveBeenCalled();
    expect(field("Name")).toHaveValue("Gold");
  });
});

describe("CategoryManager move via select", () => {
  it("offers Top level and every category except self, descendants and held leaves", () => {
    setup(nested);
    expect(optionNames(moveSelect("Spare"))).toEqual([
      "Top level",
      "Stocks",
      "Core",
      "US Stocks",
      "International",
    ]);
    expect(optionNames(moveSelect("Stocks"))).toEqual(["Top level", "Spare"]);
    expect(optionNames(moveSelect("Core"))).toEqual([
      "Top level",
      "Stocks",
      "International",
      "Spare",
    ]);
    expect(moveSelect("US Stocks")).toHaveValue("Core");
    expect(moveSelect("Bonds")).toHaveValue("");
  });

  it("moves a category into another and confirms in the status line", async () => {
    const { user, onChange } = setup(nested);
    await user.selectOptions(moveSelect("International"), "Spare");

    expect(updateCategory).toHaveBeenCalledWith("International", { parent: "Spare" });
    await waitFor(() => expect(onChange).toHaveBeenCalledWith(updated));
    expect(await screen.findByRole("status")).toHaveTextContent(/moved.*international.*spare/i);
  });

  it("moves a parent to the top level with parent: null", async () => {
    const { user } = setup(nested);
    await user.selectOptions(moveSelect("Core"), "Top level");
    expect(updateCategory).toHaveBeenCalledWith("Core", { parent: null });
  });

  it("shows the error on the row and reverts the select when the move fails", async () => {
    vi.mocked(updateCategory).mockRejectedValue(new Error("Boom"));
    const { user, onChange } = setup(nested);
    await user.selectOptions(moveSelect("International"), "Spare");

    expect(await within(rowItem("International")).findByRole("alert")).toHaveTextContent("Boom");
    expect(onChange).not.toHaveBeenCalled();
    expect(moveSelect("International")).toHaveValue("Stocks");
  });
});

describe("CategoryManager drag and drop", () => {
  it("makes rows draggable", () => {
    setup(nested);
    expect(row("Bonds")).toHaveAttribute("draggable", "true");
    expect(row("Core")).toHaveAttribute("draggable", "true");
  });

  it("moves a category onto another row, including an empty leaf", async () => {
    const { onChange } = setup(nested);
    await dnd.drag(row("International"), row("Spare"));

    expect(updateCategory).toHaveBeenCalledWith("International", { parent: "Spare" });
    await waitFor(() => expect(onChange).toHaveBeenCalledWith(updated));
  });

  it("moves a parent onto another category", async () => {
    setup(nested);
    await dnd.drag(row("Core"), row("Spare"));
    expect(updateCategory).toHaveBeenCalledWith("Core", { parent: "Spare" });
  });

  it("moves a nested row to the top level via the Top level zone", async () => {
    setup(nested);
    await dnd.drag(row("US Stocks"), topZone());
    expect(updateCategory).toHaveBeenCalledWith("US Stocks", { parent: null });
  });

  it("accepts valid targets and ignores self, descendants and leaves holding securities", async () => {
    setup(nested);
    await fireEvent.dragStart(row("Stocks"));
    expect(await fireEvent.dragOver(row("Spare"))).toBe(false); // accepted
    expect(await fireEvent.dragOver(row("Stocks"))).toBe(true); // self
    expect(await fireEvent.dragOver(row("Core"))).toBe(true); // descendant
    expect(await fireEvent.dragOver(row("Bonds"))).toBe(true); // holds securities
    await fireEvent.dragEnd(row("Stocks"));

    await dnd.drag(row("Spare"), row("Bonds"));
    await dnd.drag(row("International"), row("Stocks")); // current parent
    await dnd.drag(row("Bonds"), topZone()); // already top level
    expect(updateCategory).not.toHaveBeenCalled();
  });

  it("highlights valid targets while dragging and clears on drag end", async () => {
    setup(nested);
    await fireEvent.dragStart(row("Stocks"));

    expect(row("Spare")).toHaveClass("drop-ok");
    expect(topZone()).not.toHaveClass("drop-ok"); // already top level: no-op
    expect(row("Bonds")).not.toHaveClass("drop-ok"); // holds securities
    expect(row("Stocks")).not.toHaveClass("drop-ok");
    expect(row("Core")).not.toHaveClass("drop-ok");

    await fireEvent.dragOver(row("Spare"));
    expect(row("Spare")).toHaveClass("drop-over");

    await fireEvent.dragEnd(row("Stocks"));
    expect(row("Spare")).not.toHaveClass("drop-ok");
    expect(row("Spare")).not.toHaveClass("drop-over");
  });

  it("highlights the Top level zone for a nested category", async () => {
    setup(nested);
    await fireEvent.dragStart(row("US Stocks"));
    expect(topZone()).toHaveClass("drop-ok");
    expect(row("Core")).not.toHaveClass("drop-ok"); // current parent
    expect(row("Stocks")).toHaveClass("drop-ok");
  });

  it("shows a failed drop as a row error", async () => {
    vi.mocked(updateCategory).mockRejectedValue(new Error("Boom"));
    const { onChange } = setup(nested);
    await dnd.drag(row("International"), row("Spare"));

    expect(await within(rowItem("International")).findByRole("alert")).toHaveTextContent("Boom");
    expect(onChange).not.toHaveBeenCalled();
  });
});

describe("CategoryManager edit", () => {
  it("pre-fills the row editor and cancels without calling the API", async () => {
    const { user } = setup();
    await user.click(screen.getByRole("button", { name: "Edit US Stocks" }));

    expect(screen.getByLabelText("Name for US Stocks")).toHaveValue("US Stocks");
    expect(screen.getByLabelText("Buy symbol for US Stocks")).toHaveValue("VTI");
    expect(screen.getByLabelText("Default target for US Stocks")).toHaveValue(48);

    await user.type(screen.getByLabelText("Name for US Stocks"), " X");
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.queryByLabelText("Name for US Stocks")).toBeNull();
    expect(row("US Stocks")).toBeInTheDocument();
    expect(updateCategory).not.toHaveBeenCalled();
  });

  it("renames by sending only the changed field", async () => {
    const { user, onChange } = setup();
    await user.click(screen.getByRole("button", { name: "Edit US Stocks" }));
    const name = screen.getByLabelText("Name for US Stocks");
    await user.clear(name);
    await user.type(name, "Domestic");
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(updateCategory).toHaveBeenCalledWith("US Stocks", { name: "Domestic" });
    await waitFor(() => expect(onChange).toHaveBeenCalledWith(updated));
    expect(screen.queryByLabelText("Name for Domestic")).toBeNull();
  });

  it("sends target: null when the target is cleared", async () => {
    const { user } = setup();
    await user.click(screen.getByRole("button", { name: "Edit Bonds" }));
    await user.clear(screen.getByLabelText("Default target for Bonds"));
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(updateCategory).toHaveBeenCalledWith("Bonds", { target: null });
  });

  it("sends buy_symbol: null when the symbol is cleared", async () => {
    const { user } = setup();
    await user.click(screen.getByRole("button", { name: "Edit Bonds" }));
    await user.clear(screen.getByLabelText("Buy symbol for Bonds"));
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(updateCategory).toHaveBeenCalledWith("Bonds", { buy_symbol: null });
  });

  it("lets a parent have an optional buy symbol, with a hint", async () => {
    const { user } = setup(nested);
    await user.click(screen.getByRole("button", { name: "Edit Stocks" }));

    expect(screen.getByLabelText("Buy symbol for Stocks")).toHaveValue("");
    expect(screen.getByText(/used when this category holds securities/i)).toBeInTheDocument();
    await user.type(screen.getByLabelText("Buy symbol for Stocks"), "vt");
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(updateCategory).toHaveBeenCalledWith("Stocks", { buy_symbol: "VT" });
  });

  it("rejects an invalid name without calling the API", async () => {
    const { user } = setup(nested);
    await user.click(screen.getByRole("button", { name: "Edit Stocks" }));
    await user.type(screen.getByLabelText("Name for Stocks"), "/");
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(await within(rowItem("Stocks")).findByRole("alert")).toBeInTheDocument();
    expect(updateCategory).not.toHaveBeenCalled();
  });

  it("shows a server error in the row and stays in edit mode", async () => {
    vi.mocked(updateCategory).mockRejectedValue(new Error("Category 'Bonds' already exists"));
    const { user, onChange } = setup();
    await user.click(screen.getByRole("button", { name: "Edit US Stocks" }));
    const name = screen.getByLabelText("Name for US Stocks");
    await user.clear(name);
    await user.type(name, "Bonds");
    await user.click(screen.getByRole("button", { name: "Save" }));

    const alert = await within(rowItem("US Stocks")).findByRole("alert");
    expect(alert).toHaveTextContent("Category 'Bonds' already exists");
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Name for US Stocks")).toBeInTheDocument();
  });
});

describe("CategoryManager delete", () => {
  it("deletes a category and reports the server's config", async () => {
    const { user, onChange } = setup();
    await user.click(screen.getByRole("button", { name: "Delete Bonds" }));

    expect(deleteCategory).toHaveBeenCalledWith("Bonds");
    await waitFor(() => expect(onChange).toHaveBeenCalledWith(updated));
  });

  it("notes that sub-categories move up a level only when some exist", () => {
    setup(nested);
    expect(screen.getByText(/children move up a level/i)).toBeInTheDocument();
  });

  it("omits the move-up note for a flat config", () => {
    setup();
    expect(screen.queryByText(/children move up a level/i)).toBeNull();
  });

  it("shows the 409 in-use message on that row", async () => {
    const message = "Category 'Bonds' is in use by BND";
    vi.mocked(deleteCategory).mockRejectedValue(new Error(message));
    const { user, onChange } = setup();
    await user.click(screen.getByRole("button", { name: "Delete Bonds" }));

    expect(await within(rowItem("Bonds")).findByRole("alert")).toHaveTextContent(message);
    expect(onChange).not.toHaveBeenCalled();
    expect(row("Bonds")).toBeInTheDocument();
  });
});
