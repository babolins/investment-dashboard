import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  createCategory,
  createGroup,
  deleteCategory,
  deleteGroup,
  fetchAllocation,
  fetchConfig,
  fetchRebalance,
  setAssignment,
  updateCategory,
  updateGroup,
  uploadPortfolio,
} from "./api";
import { allocation, config, groupedConfig, portfolio, rebalance } from "../test/fixtures";

const fetchMock = vi.fn();

function respond(body: unknown, status = 200): void {
  fetchMock.mockResolvedValueOnce(
    new Response(typeof body === "string" ? body : JSON.stringify(body), { status }),
  );
}

/** The (url, init) of the single fetch call made by the function under test. */
function lastCall(): [string, RequestInit] {
  expect(fetchMock).toHaveBeenCalledTimes(1);
  const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit | undefined];
  return [url, init ?? {}];
}

function jsonBody(init: RequestInit): unknown {
  return JSON.parse(init.body as string);
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("fetchConfig", () => {
  it("GETs /api/config", async () => {
    respond(config);
    await expect(fetchConfig()).resolves.toEqual(config);
    const [url, init] = lastCall();
    expect(url).toBe("/api/config");
    expect(init.method ?? "GET").toBe("GET");
  });
});

describe("uploadPortfolio", () => {
  it("POSTs the file as form data", async () => {
    respond({ portfolio, allocation });
    const file = new File(["x"], "p.csv", { type: "text/csv" });
    await uploadPortfolio(file);
    const [url, init] = lastCall();
    expect(url).toBe("/api/upload");
    expect(init.method).toBe("POST");
    expect((init.body as FormData).get("file")).toBe(file);
  });
});

describe("fetchAllocation", () => {
  it("POSTs the portfolio as JSON to /api/allocation", async () => {
    respond(allocation);
    await expect(fetchAllocation(portfolio)).resolves.toEqual(allocation);
    const [url, init] = lastCall();
    expect(url).toBe("/api/allocation");
    expect(init.method).toBe("POST");
    expect(init.headers).toEqual({ "Content-Type": "application/json" });
    expect(jsonBody(init)).toEqual(portfolio);
  });
});

describe("fetchRebalance", () => {
  it("POSTs the request merged with the allocation", async () => {
    respond(rebalance);
    const target = { "US Stocks": 48, International: 32, Bonds: 20 };
    await expect(fetchRebalance(allocation, { investment_amount: 1000, target })).resolves.toEqual(
      rebalance,
    );
    const [url, init] = lastCall();
    expect(url).toBe("/api/rebalance");
    expect(init.method).toBe("POST");
    expect(jsonBody(init)).toEqual({ investment_amount: 1000, target, ...allocation });
  });
});

describe("createCategory", () => {
  it("POSTs the input and accepts a 201", async () => {
    respond(config, 201);
    const input = { name: "Real Estate", buy_symbol: "VNQ", target: null };
    await expect(createCategory(input)).resolves.toEqual(config);
    const [url, init] = lastCall();
    expect(url).toBe("/api/categories");
    expect(init.method).toBe("POST");
    expect(init.headers).toEqual({ "Content-Type": "application/json" });
    expect(jsonBody(init)).toEqual(input);
  });
});

describe("updateCategory", () => {
  it("PATCHes with the encoded category name", async () => {
    respond(config);
    await expect(updateCategory("US Stocks", { buy_symbol: "VOO" })).resolves.toEqual(config);
    const [url, init] = lastCall();
    expect(url).toBe("/api/categories/US%20Stocks");
    expect(init.method).toBe("PATCH");
    expect(jsonBody(init)).toEqual({ buy_symbol: "VOO" });
  });

  it("sends only the given keys and an explicit null target", async () => {
    respond(config);
    await updateCategory("Bonds", { target: null });
    expect(jsonBody(lastCall()[1])).toEqual({ target: null });
  });

  it("serialises an explicit null parent (move to top level)", async () => {
    respond(config);
    await updateCategory("US Stocks", { parent: null });
    expect(jsonBody(lastCall()[1])).toEqual({ parent: null });
    expect(lastCall()[1].body).toBe('{"parent":null}');
  });

  it("sends a parent group name", async () => {
    respond(groupedConfig);
    await updateCategory("Bonds", { parent: "Fixed Income" });
    expect(jsonBody(lastCall()[1])).toEqual({ parent: "Fixed Income" });
  });

  it("encodes reserved characters in the name", async () => {
    respond(config);
    await updateCategory("R&D #1?", { name: "New" });
    expect(lastCall()[0]).toBe("/api/categories/R%26D%20%231%3F");
  });
});

describe("deleteCategory", () => {
  it("DELETEs the encoded name without a body", async () => {
    respond(config);
    await expect(deleteCategory("US Stocks")).resolves.toEqual(config);
    const [url, init] = lastCall();
    expect(url).toBe("/api/categories/US%20Stocks");
    expect(init.method).toBe("DELETE");
    expect(init.body).toBeUndefined();
  });
});

describe("createGroup", () => {
  it("POSTs the input to /api/groups and accepts a 201", async () => {
    respond(groupedConfig, 201);
    const input = { name: "Stocks", parent: null, target: 60 };
    await expect(createGroup(input)).resolves.toEqual(groupedConfig);
    const [url, init] = lastCall();
    expect(url).toBe("/api/groups");
    expect(init.method).toBe("POST");
    expect(init.headers).toEqual({ "Content-Type": "application/json" });
    expect(jsonBody(init)).toEqual(input);
  });

  it("sends a parent and a null target", async () => {
    respond(groupedConfig, 201);
    await createGroup({ name: "Intl", parent: "Stocks", target: null });
    expect(jsonBody(lastCall()[1])).toEqual({ name: "Intl", parent: "Stocks", target: null });
  });
});

describe("updateGroup", () => {
  it("PATCHes the encoded group name with only the given keys", async () => {
    respond(groupedConfig);
    await expect(updateGroup("Fixed Income", { name: "Bonds" })).resolves.toEqual(groupedConfig);
    const [url, init] = lastCall();
    expect(url).toBe("/api/groups/Fixed%20Income");
    expect(init.method).toBe("PATCH");
    expect(jsonBody(init)).toEqual({ name: "Bonds" });
  });

  it("serialises explicit null parent and target", async () => {
    respond(groupedConfig);
    await updateGroup("Stocks", { parent: null, target: null });
    expect(lastCall()[1].body).toBe('{"parent":null,"target":null}');
  });

  it("encodes reserved characters in the name", async () => {
    respond(groupedConfig);
    await updateGroup("R&D #1?", { target: 5 });
    expect(lastCall()[0]).toBe("/api/groups/R%26D%20%231%3F");
  });
});

describe("deleteGroup", () => {
  it("DELETEs the encoded name without a body", async () => {
    respond(config);
    await expect(deleteGroup("Fixed Income")).resolves.toEqual(config);
    const [url, init] = lastCall();
    expect(url).toBe("/api/groups/Fixed%20Income");
    expect(init.method).toBe("DELETE");
    expect(init.body).toBeUndefined();
  });

  it("surfaces the server's error message", async () => {
    respond({ detail: "Group 'X' not found" }, 404);
    await expect(deleteGroup("X")).rejects.toThrow("Group 'X' not found");
  });
});

describe("setAssignment", () => {
  it("PUTs weights to the encoded symbol", async () => {
    respond(config);
    const update = { weights: { "US Stocks": 0.7, International: 0.3 } };
    await expect(setAssignment("BRK.B", update)).resolves.toEqual(config);
    const [url, init] = lastCall();
    expect(url).toBe("/api/assignments/BRK.B");
    expect(init.method).toBe("PUT");
    expect(jsonBody(init)).toEqual(update);
  });

  it("PUTs an exclusion", async () => {
    respond(config);
    await setAssignment("A B", { excluded: true });
    const [url, init] = lastCall();
    expect(url).toBe("/api/assignments/A%20B");
    expect(jsonBody(init)).toEqual({ excluded: true });
  });
});

describe("error handling", () => {
  it("uses a string detail as the message", async () => {
    respond({ detail: "Category 'X' not found" }, 404);
    await expect(deleteCategory("X")).rejects.toThrow("Category 'X' not found");
  });

  it("joins messages from a FastAPI list-shaped 422 detail", async () => {
    respond(
      {
        detail: [
          { type: "value_error", loc: ["body", "name"], msg: "Value error, Name is too long" },
          { type: "greater_than", loc: ["body", "target"], msg: "Input should be at most 100" },
        ],
      },
      422,
    );
    await expect(createCategory({ name: "x", buy_symbol: "X", target: 1 })).rejects.toThrow(
      "Name is too long; Input should be at most 100",
    );
  });

  it("never renders object details as [object Object]", async () => {
    respond({ detail: [{ type: "missing", loc: ["body"], msg: "Field required" }] }, 422);
    const err = await fetchAllocation(portfolio).catch((e: Error) => e);
    expect((err as Error).message).toBe("Field required");
  });

  it("falls back to the HTTP status when the body is not JSON", async () => {
    respond("Internal Server Error", 500);
    await expect(fetchConfig()).rejects.toThrow("HTTP 500");
  });

  it("falls back to the HTTP status when there is no usable detail", async () => {
    respond({ detail: [] }, 422);
    await expect(fetchConfig()).rejects.toThrow("HTTP 422");
  });
});
