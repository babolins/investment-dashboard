import { render, screen, waitFor, within } from "@testing-library/svelte";
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
  vi.mocked(createCategory).mockResolvedValue(updated);
  vi.mocked(updateCategory).mockResolvedValue(updated);
  vi.mocked(deleteCategory).mockResolvedValue(updated);
});

function setup(cfg: ConfigSummary = config) {
  const onChange = vi.fn();
  render(CategoryManager, { props: { config: cfg, onChange } });
  return { onChange, user: userEvent.setup() };
}

const row = (name: string) =>
  screen.getByText(name, { selector: "li *" }).closest("li") as HTMLElement;

function withCategories(count: number): ConfigSummary {
  return {
    ...config,
    categories: Array.from({ length: count }, (_, i) => ({
      name: `Cat ${i}`,
      buy_symbol: "VTI",
      target: null,
      color: "#2a78d6",
    })),
  };
}

describe("CategoryManager list", () => {
  it("lists each category in order with buy symbol and default target", () => {
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

  it("shows a dash for a category without a default target", () => {
    setup(withCategories(1));
    expect(row("Cat 0")).toHaveTextContent("—");
  });

  it("confirms when default targets total 100%", () => {
    setup();
    expect(screen.getByText(/default targets total 100%/i)).toBeInTheDocument();
  });

  it("warns when default targets do not total 100%", () => {
    const cfg = { ...config, categories: config.categories.slice(0, 2) };
    setup(cfg);
    expect(screen.getByText(/default targets total 80%/i)).toHaveTextContent(/not 100%/);
  });
});

describe("CategoryManager add", () => {
  async function fill(
    user: ReturnType<typeof userEvent.setup>,
    name: string,
    symbol: string,
    target = "",
  ) {
    await user.type(screen.getByLabelText("Name"), name);
    await user.type(screen.getByLabelText("Buy symbol"), symbol);
    if (target) await user.type(screen.getByLabelText("Default target (%)"), target);
  }

  it("creates a category, uppercasing the symbol, and reports the server's config", async () => {
    const { user, onChange } = setup();
    await fill(user, "  Gold ", "gld", "5");
    await user.click(screen.getByRole("button", { name: "Add category" }));

    expect(createCategory).toHaveBeenCalledWith({ name: "Gold", buy_symbol: "GLD", target: 5 });
    await waitFor(() => expect(onChange).toHaveBeenCalledWith(updated));
    expect(screen.getByLabelText("Name")).toHaveValue("");
    expect(screen.getByLabelText("Buy symbol")).toHaveValue("");
  });

  it("sends a null target when left blank", async () => {
    const { user } = setup();
    await fill(user, "Gold", "GLD");
    await user.click(screen.getByRole("button", { name: "Add category" }));
    expect(createCategory).toHaveBeenCalledWith({ name: "Gold", buy_symbol: "GLD", target: null });
  });

  it("rejects a blank name without calling the API", async () => {
    const { user } = setup();
    await user.type(screen.getByLabelText("Buy symbol"), "GLD");
    await user.click(screen.getByRole("button", { name: "Add category" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(createCategory).not.toHaveBeenCalled();
  });

  it("rejects a name that duplicates an existing one, ignoring case", async () => {
    const { user } = setup();
    await fill(user, "bonds", "AGG");
    await user.click(screen.getByRole("button", { name: "Add category" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(createCategory).not.toHaveBeenCalled();
  });

  it("rejects a malformed buy symbol", async () => {
    const { user } = setup();
    await fill(user, "Gold", "not a symbol");
    await user.click(screen.getByRole("button", { name: "Add category" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(createCategory).not.toHaveBeenCalled();
  });

  it("rejects a target outside 0-100", async () => {
    const { user } = setup();
    await fill(user, "Gold", "GLD", "150");
    await user.click(screen.getByRole("button", { name: "Add category" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(createCategory).not.toHaveBeenCalled();
  });

  it("shows a server error inline and keeps the form", async () => {
    vi.mocked(createCategory).mockRejectedValue(new Error("Category 'Gold' already exists"));
    const { user, onChange } = setup();
    await fill(user, "Gold", "GLD");
    await user.click(screen.getByRole("button", { name: "Add category" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Category 'Gold' already exists");
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Name")).toHaveValue("Gold");
  });

  it("disables Add at 8 categories with a hint, but not at 7", () => {
    const { unmount } = render(CategoryManager, {
      props: { config: withCategories(7), onChange: vi.fn() },
    });
    expect(screen.getByRole("button", { name: "Add category" })).toBeEnabled();
    unmount();

    render(CategoryManager, { props: { config: withCategories(8), onChange: vi.fn() } });
    expect(screen.getByRole("button", { name: "Add category" })).toBeDisabled();
    expect(screen.getByText(/maximum of 8 categories/i)).toBeInTheDocument();
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

  it("closes without calling the API when nothing changed", async () => {
    const { user, onChange } = setup();
    await user.click(screen.getByRole("button", { name: "Edit Bonds" }));
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(updateCategory).not.toHaveBeenCalled();
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.queryByLabelText("Name for Bonds")).toBeNull();
  });

  it("shows a server error in the row and stays in edit mode", async () => {
    vi.mocked(updateCategory).mockRejectedValue(new Error("Category 'Bonds' already exists"));
    const { user, onChange } = setup();
    await user.click(screen.getByRole("button", { name: "Edit US Stocks" }));
    const name = screen.getByLabelText("Name for US Stocks");
    await user.clear(name);
    await user.type(name, "Bonds");
    await user.click(screen.getByRole("button", { name: "Save" }));

    const alert = await within(row("US Stocks")).findByRole("alert");
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

    expect(await within(row("Bonds")).findByRole("alert")).toHaveTextContent(message);
    expect(onChange).not.toHaveBeenCalled();
    expect(row("Bonds")).toBeInTheDocument();
  });
});
