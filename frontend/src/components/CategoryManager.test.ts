import { fireEvent, render, screen, waitFor, within } from "@testing-library/svelte";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import CategoryManager from "./CategoryManager.svelte";
import {
  createCategory,
  createGroup,
  deleteCategory,
  deleteGroup,
  updateCategory,
  updateGroup,
} from "../services/api";
import { config, groupedConfig } from "../test/fixtures";
import type { ConfigSummary } from "../types";

vi.mock("../services/api", () => ({
  createCategory: vi.fn(),
  updateCategory: vi.fn(),
  deleteCategory: vi.fn(),
  createGroup: vi.fn(),
  updateGroup: vi.fn(),
  deleteGroup: vi.fn(),
}));

// What the server would return after a mutation; passed through untouched.
const updated: ConfigSummary = { ...config, exclusions: [] };

beforeEach(() => {
  vi.resetAllMocks();
  for (const fn of [createCategory, updateCategory, deleteCategory]) {
    vi.mocked(fn).mockResolvedValue(updated);
  }
  for (const fn of [createGroup, updateGroup, deleteGroup]) {
    vi.mocked(fn).mockResolvedValue(updated);
  }
});

// Stocks (top) > Core (50%) > US Stocks, Stocks > International, Bonds (top), Spare (empty, top).
const nested: ConfigSummary = {
  ...groupedConfig,
  groups: [
    { name: "Stocks", parent: null, target: 60 },
    { name: "Core", parent: "Stocks", target: 50 },
    { name: "Spare", parent: null, target: null },
  ],
  categories: [
    { ...groupedConfig.categories[0], parent: "Core" },
    groupedConfig.categories[1],
    groupedConfig.categories[2],
  ],
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

function withCategories(count: number): ConfigSummary {
  return {
    ...config,
    categories: Array.from({ length: count }, (_, i) => ({
      name: `Cat ${i}`,
      buy_symbol: "VTI",
      parent: null,
      target: null,
      color: "#2a78d6",
    })),
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

  it("renders groups as a tree: groups first, children nested inside their group", () => {
    setup(nested);
    const names = screen.getAllByRole("group").map((g) => g.getAttribute("aria-label"));
    expect(names).toEqual([
      "Top level",
      "Stocks",
      "Core",
      "US Stocks",
      "International",
      "Spare",
      "Bonds",
    ]);

    expect(within(rowItem("Stocks")).getByText("Core", { selector: "strong" })).toBeInTheDocument();
    expect(within(rowItem("Core")).getByText("US Stocks")).toBeInTheDocument();
    expect(within(rowItem("Spare")).queryByText("Bonds")).toBeNull();
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

  it("shows a group's default share and direct child count, including empty groups", () => {
    setup(nested);
    expect(row("Stocks")).toHaveTextContent("60%");
    expect(row("Stocks")).toHaveTextContent(/2 items/);
    expect(row("Spare")).toHaveTextContent("—");
    expect(row("Spare")).toHaveTextContent(/empty|0 items/);
    expect(row("US Stocks")).toHaveTextContent("70%");
    expect(row("US Stocks")).toHaveTextContent("VTI");
  });

  it("confirms per level when default targets total 100%", () => {
    setup(groupedConfig);
    expect(screen.getByText(/top level targets total 100%/i)).toBeInTheDocument();
    expect(screen.getByText(/stocks targets total 100%/i)).toBeInTheDocument();
  });

  it("warns for the level whose targets do not total 100%", () => {
    const cfg = { ...config, categories: config.categories.slice(0, 2) };
    setup(cfg);
    expect(screen.getByText(/top level targets total 80%/i)).toHaveTextContent(/not 100%/);
  });

  it("warns only for the offending group", () => {
    const cfg = {
      ...groupedConfig,
      categories: groupedConfig.categories.map((c) =>
        c.name === "International" ? { ...c, target: 20 } : c,
      ),
    };
    setup(cfg);
    expect(screen.getByText(/stocks targets total 90%/i)).toHaveTextContent(/not 100%/);
    expect(screen.getByText(/top level targets total 100%/i)).not.toHaveTextContent(/not 100%/);
  });
});

describe("CategoryManager add group", () => {
  const form = () => screen.getByRole("form", { name: "Add group" });
  const field = (label: string) => within(form()).getByLabelText(label);
  const submit = async (user: User) =>
    user.click(within(form()).getByRole("button", { name: "Add group" }));

  it("creates a top-level group and clears the form", async () => {
    const { user, onChange } = setup(groupedConfig);
    await user.type(field("Name"), "  Fixed Income ");
    await user.type(field("Default % of parent"), "40");
    await submit(user);

    expect(createGroup).toHaveBeenCalledWith({ name: "Fixed Income", parent: null, target: 40 });
    await waitFor(() => expect(onChange).toHaveBeenCalledWith(updated));
    expect(field("Name")).toHaveValue("");
  });

  it("creates a group inside a parent group with no target", async () => {
    const { user } = setup(groupedConfig);
    await user.type(field("Name"), "Intl");
    await user.selectOptions(field("Parent group"), "Stocks");
    await submit(user);

    expect(createGroup).toHaveBeenCalledWith({ name: "Intl", parent: "Stocks", target: null });
  });

  it.each([
    ["a blank name", "", "10"],
    ["a name containing a slash", "a/b", "10"],
    ["a reserved name", "Unassigned", "10"],
    ["a name taken by a category (any case)", "bonds", "10"],
    ["a name taken by a group (any case)", "stocks", "10"],
    ["a target above 100", "Fine", "150"],
  ])("rejects %s without calling the API", async (_label, name, target) => {
    const { user } = setup(groupedConfig);
    if (name) await user.type(field("Name"), name);
    await user.type(field("Default % of parent"), target);
    await submit(user);

    expect(await within(form()).findByRole("alert")).toBeInTheDocument();
    expect(createGroup).not.toHaveBeenCalled();
  });

  it("shows a server error inline and keeps the form", async () => {
    vi.mocked(createGroup).mockRejectedValue(new Error("Group 'Gold' already exists"));
    const { user, onChange } = setup();
    await user.type(field("Name"), "Gold");
    await submit(user);

    expect(await within(form()).findByRole("alert")).toHaveTextContent(
      "Group 'Gold' already exists",
    );
    expect(onChange).not.toHaveBeenCalled();
    expect(field("Name")).toHaveValue("Gold");
  });

  it("is still enabled at 8 categories, since groups do not count toward the cap", () => {
    setup({ ...withCategories(8), groups: [] });
    expect(within(form()).getByRole("button", { name: "Add group" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Add category" })).toBeDisabled();
  });
});

describe("CategoryManager add category", () => {
  const form = () => screen.getByRole("form", { name: "Add category" });
  const field = (label: string) => within(form()).getByLabelText(label);

  async function fill(user: User, name: string, symbol: string, target = "") {
    await user.type(field("Name"), name);
    await user.type(field("Buy symbol"), symbol);
    if (target) await user.type(field("Default % of parent"), target);
  }

  it("creates a category, uppercasing the symbol, and reports the server's config", async () => {
    const { user, onChange } = setup();
    await fill(user, "  Gold ", "gld", "5");
    await user.click(within(form()).getByRole("button", { name: "Add category" }));

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

  it("creates a category directly inside the chosen group", async () => {
    const { user } = setup(groupedConfig);
    await fill(user, "Gold", "GLD", "5");
    await user.selectOptions(field("Group"), "Stocks");
    await user.click(within(form()).getByRole("button", { name: "Add category" }));
    expect(createCategory).toHaveBeenCalledWith({
      name: "Gold",
      buy_symbol: "GLD",
      target: 5,
      parent: "Stocks",
    });
  });

  it("sends a null target when left blank", async () => {
    const { user } = setup();
    await fill(user, "Gold", "GLD");
    await user.click(within(form()).getByRole("button", { name: "Add category" }));
    expect(createCategory).toHaveBeenCalledWith({
      name: "Gold",
      buy_symbol: "GLD",
      target: null,
      parent: null,
    });
  });

  it("rejects a blank name without calling the API", async () => {
    const { user } = setup();
    await user.type(field("Buy symbol"), "GLD");
    await user.click(within(form()).getByRole("button", { name: "Add category" }));
    expect(await within(form()).findByRole("alert")).toBeInTheDocument();
    expect(createCategory).not.toHaveBeenCalled();
  });

  it("shows a server error inline and keeps the form", async () => {
    vi.mocked(createCategory).mockRejectedValue(new Error("Category 'Gold' already exists"));
    const { user, onChange } = setup();
    await fill(user, "Gold", "GLD");
    await user.click(within(form()).getByRole("button", { name: "Add category" }));

    expect(await within(form()).findByRole("alert")).toHaveTextContent(
      "Category 'Gold' already exists",
    );
    expect(onChange).not.toHaveBeenCalled();
    expect(field("Name")).toHaveValue("Gold");
  });

  it("disables Add at 8 categories with a hint, but not at 7", () => {
    const { unmount } = render(CategoryManager, {
      props: { config: withCategories(7), onChange: vi.fn() },
    });
    expect(within(form()).getByRole("button", { name: "Add category" })).toBeEnabled();
    unmount();

    render(CategoryManager, { props: { config: withCategories(8), onChange: vi.fn() } });
    expect(within(form()).getByRole("button", { name: "Add category" })).toBeDisabled();
    expect(screen.getByText(/maximum of 8 categories/i)).toBeInTheDocument();
  });
});

describe("CategoryManager group edit and delete", () => {
  it("pre-fills the group editor without a buy symbol and saves only changed fields", async () => {
    const { user, onChange } = setup(nested);
    await user.click(screen.getByRole("button", { name: "Edit Stocks" }));

    expect(screen.getByLabelText("Name for Stocks")).toHaveValue("Stocks");
    expect(screen.getByLabelText("Default target for Stocks")).toHaveValue(60);
    expect(screen.queryByLabelText("Buy symbol for Stocks")).toBeNull();
    expect(row("Stocks")).toHaveAttribute("draggable", "false");

    const name = screen.getByLabelText("Name for Stocks");
    await user.clear(name);
    await user.type(name, "Equities");
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(updateGroup).toHaveBeenCalledWith("Stocks", { name: "Equities" });
    await waitFor(() => expect(onChange).toHaveBeenCalledWith(updated));
  });

  it("closes without calling the API when nothing changed or on cancel", async () => {
    const { user } = setup(nested);
    await user.click(screen.getByRole("button", { name: "Edit Stocks" }));
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(screen.queryByLabelText("Name for Stocks")).toBeNull();

    await user.click(screen.getByRole("button", { name: "Edit Stocks" }));
    await user.type(screen.getByLabelText("Name for Stocks"), "X");
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByLabelText("Name for Stocks")).toBeNull();
    expect(updateGroup).not.toHaveBeenCalled();
  });

  it("rejects an invalid group name or target without calling the API", async () => {
    const { user } = setup(nested);
    await user.click(screen.getByRole("button", { name: "Edit Stocks" }));
    await user.type(screen.getByLabelText("Name for Stocks"), "/");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(await within(rowItem("Stocks")).findByRole("alert")).toBeInTheDocument();
    expect(updateGroup).not.toHaveBeenCalled();
  });

  it("deletes a group, notes that children move up, and reports the server's config", async () => {
    const { user, onChange } = setup(nested);
    expect(screen.getByText(/children move up a level/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Delete Stocks" }));

    expect(deleteGroup).toHaveBeenCalledWith("Stocks");
    await waitFor(() => expect(onChange).toHaveBeenCalledWith(updated));
  });

  it("shows a delete failure on the group's row", async () => {
    vi.mocked(deleteGroup).mockRejectedValue(new Error("Group not found"));
    const { user, onChange } = setup(nested);
    await user.click(screen.getByRole("button", { name: "Delete Spare" }));

    expect(await within(rowItem("Spare")).findByRole("alert")).toHaveTextContent("Group not found");
    expect(onChange).not.toHaveBeenCalled();
  });
});

describe("CategoryManager move via select", () => {
  it("offers Top level and every group to a category", () => {
    setup(nested);
    expect(optionNames(moveSelect("Bonds"))).toEqual(["Top level", "Stocks", "Core", "Spare"]);
    expect(moveSelect("US Stocks")).toHaveValue("Core");
    expect(moveSelect("Bonds")).toHaveValue("");
  });

  it("excludes a group itself and its descendants", () => {
    setup(nested);
    expect(optionNames(moveSelect("Stocks"))).toEqual(["Top level", "Spare"]);
    expect(optionNames(moveSelect("Core"))).toEqual(["Top level", "Stocks", "Spare"]);
  });

  it("moves a category into a group and confirms in the status line", async () => {
    const { user, onChange } = setup(nested);
    await user.selectOptions(moveSelect("Bonds"), "Spare");

    expect(updateCategory).toHaveBeenCalledWith("Bonds", { parent: "Spare" });
    await waitFor(() => expect(onChange).toHaveBeenCalledWith(updated));
    expect(await screen.findByRole("status")).toHaveTextContent(/moved.*bonds.*spare/i);
  });

  it("moves a group to the top level with parent: null", async () => {
    const { user } = setup(nested);
    await user.selectOptions(moveSelect("Core"), "Top level");
    expect(updateGroup).toHaveBeenCalledWith("Core", { parent: null });
  });

  it("shows the error on the row and reverts the select when the move fails", async () => {
    vi.mocked(updateCategory).mockRejectedValue(new Error("Boom"));
    const { user, onChange } = setup(nested);
    await user.selectOptions(moveSelect("Bonds"), "Spare");

    expect(await within(rowItem("Bonds")).findByRole("alert")).toHaveTextContent("Boom");
    expect(onChange).not.toHaveBeenCalled();
    expect(moveSelect("Bonds")).toHaveValue("");
  });
});

describe("CategoryManager drag and drop", () => {
  it("makes rows draggable", () => {
    setup(nested);
    expect(row("Bonds")).toHaveAttribute("draggable", "true");
    expect(row("Core")).toHaveAttribute("draggable", "true");
  });

  it("moves a category onto a group row", async () => {
    const { onChange } = setup(nested);
    await dnd.drag(row("Bonds"), row("Spare"));

    expect(updateCategory).toHaveBeenCalledWith("Bonds", { parent: "Spare" });
    await waitFor(() => expect(onChange).toHaveBeenCalledWith(updated));
  });

  it("moves a group onto another group", async () => {
    setup(nested);
    await dnd.drag(row("Spare"), row("Core"));
    expect(updateGroup).toHaveBeenCalledWith("Spare", { parent: "Core" });
  });

  it("moves a nested row to the top level via the Top level zone", async () => {
    setup(nested);
    await dnd.drag(row("US Stocks"), topZone());
    expect(updateCategory).toHaveBeenCalledWith("US Stocks", { parent: null });

    await dnd.drag(row("Core"), topZone());
    expect(updateGroup).toHaveBeenCalledWith("Core", { parent: null });
  });

  it("accepts a valid target and ignores a group dropped on itself or a descendant", async () => {
    setup(nested);
    await fireEvent.dragStart(row("Stocks"));
    expect(await fireEvent.dragOver(row("Spare"))).toBe(false); // accepted
    expect(await fireEvent.dragOver(row("Stocks"))).toBe(true); // self
    expect(await fireEvent.dragOver(row("Core"))).toBe(true); // descendant

    await fireEvent.drop(row("Stocks"));
    await fireEvent.drop(row("Core"));
    expect(updateGroup).not.toHaveBeenCalled();
    expect(updateCategory).not.toHaveBeenCalled();
  });

  it("ignores drops on a category row and no-op drops onto the current parent", async () => {
    setup(nested);
    await dnd.drag(row("Spare"), row("Bonds"));
    await dnd.drag(row("International"), row("Stocks"));
    await dnd.drag(row("Bonds"), topZone());
    expect(updateGroup).not.toHaveBeenCalled();
    expect(updateCategory).not.toHaveBeenCalled();
  });

  it("highlights valid targets while dragging and clears on drag end", async () => {
    setup(nested);
    await fireEvent.dragStart(row("Stocks"));

    expect(row("Spare")).toHaveClass("drop-ok");
    expect(topZone()).not.toHaveClass("drop-ok"); // already top level: no-op
    expect(row("Stocks")).not.toHaveClass("drop-ok");
    expect(row("Core")).not.toHaveClass("drop-ok");

    await fireEvent.dragOver(row("Spare"));
    expect(row("Spare")).toHaveClass("drop-over");
    expect(row("Stocks")).not.toHaveClass("drop-over");

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
    await dnd.drag(row("Bonds"), row("Spare"));

    expect(await within(rowItem("Bonds")).findByRole("alert")).toHaveTextContent("Boom");
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
