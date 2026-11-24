import { fireEvent, render, screen } from "@testing-library/svelte";
import { describe, expect, it } from "vitest";
import AllocationChart from "./AllocationChart.svelte";
import { allocation, allocationWithUnassigned, colors } from "../test/fixtures";

const symbolsByCategory = {
  "US Stocks": ["FZROX", "ITOT", "VTI"],
  International: ["FZROX", "VXUS"],
  Bonds: ["BND"],
};

// The donut and its mouse handlers are presentational; the legend carries the information.
function paths(container: HTMLElement) {
  return Array.from(container.querySelectorAll("path"));
}

describe("AllocationChart", () => {
  it("shows the heading and the included value", () => {
    render(AllocationChart, { props: { breakdown: allocation, colors } });
    expect(screen.getByRole("heading", { name: "Asset Allocation" })).toBeInTheDocument();
    expect(screen.getByText(/included value \$10,000\.00/)).toBeInTheDocument();
  });

  it("draws one path per category, in order, filled with the category colour", () => {
    const { container } = render(AllocationChart, { props: { breakdown: allocation, colors } });
    expect(paths(container).map((p) => p.getAttribute("fill"))).toEqual([
      "#2a78d6", // US Stocks
      "#eb6834", // International
      "#1baf7a", // Bonds
    ]);
  });

  it("renders a legend row per category with its percentage to 1 dp", () => {
    const { container } = render(AllocationChart, { props: { breakdown: allocation, colors } });
    const rows = Array.from(container.querySelectorAll(".legend-row"));
    expect(rows.map((r) => r.querySelector(".legend-label")?.textContent)).toEqual([
      "US Stocks",
      "International",
      "Bonds",
    ]);
    expect(rows.map((r) => r.querySelector(".legend-pct")?.textContent)).toEqual([
      "60.0%",
      "30.0%",
      "10.0%",
    ]);
    expect(rows[1].querySelector(".legend-dot")).toHaveStyle({ background: "#eb6834" });
  });

  it("uses the fallback colour for a category missing from colors", () => {
    const partial = { "US Stocks": "#2a78d6" };
    const { container } = render(AllocationChart, {
      props: { breakdown: allocation, colors: partial },
    });
    expect(paths(container).map((p) => p.getAttribute("fill"))).toEqual([
      "#2a78d6",
      "#999",
      "#999",
    ]);
    const dots = Array.from(container.querySelectorAll(".legend-dot"));
    expect(dots[2]).toHaveStyle({ background: "#999" });
  });

  it("shows no tooltip until a slice is hovered", () => {
    const { container } = render(AllocationChart, { props: { breakdown: allocation, colors } });
    expect(container.querySelector(".chart-tooltip")).toBeNull();
  });

  it("shows category, value, percentage and tickers when hovering a slice", async () => {
    const { container } = render(AllocationChart, {
      props: { breakdown: allocation, colors, symbolsByCategory },
    });
    await fireEvent.mouseEnter(paths(container)[0], { clientX: 50, clientY: 40 });

    const tip = container.querySelector(".chart-tooltip") as HTMLElement;
    expect(tip).toBeInTheDocument();
    expect(tip.querySelector("strong")).toHaveTextContent("US Stocks");
    expect(tip).toHaveTextContent("$6,000.00");
    expect(tip).toHaveTextContent("60.0%");
    expect(tip.querySelector(".tooltip-tickers")).toHaveTextContent("FZROX, ITOT, VTI");
  });

  it("omits the tickers line when the category has no tickers", async () => {
    const { container } = render(AllocationChart, { props: { breakdown: allocation, colors } });
    await fireEvent.mouseEnter(paths(container)[0], { clientX: 50, clientY: 40 });
    expect(container.querySelector(".chart-tooltip")).toBeInTheDocument();
    expect(container.querySelector(".tooltip-tickers")).toBeNull();
  });

  it("switches the tooltip content when hovering another slice", async () => {
    const { container } = render(AllocationChart, {
      props: { breakdown: allocation, colors, symbolsByCategory },
    });
    await fireEvent.mouseEnter(paths(container)[0], { clientX: 50, clientY: 40 });
    await fireEvent.mouseEnter(paths(container)[1], { clientX: 60, clientY: 40 });
    const tip = container.querySelector(".chart-tooltip") as HTMLElement;
    expect(tip.querySelector("strong")).toHaveTextContent("International");
    expect(tip).toHaveTextContent("$3,000.00");
  });

  it("hides the tooltip when the pointer leaves the chart", async () => {
    const { container } = render(AllocationChart, { props: { breakdown: allocation, colors } });
    await fireEvent.mouseEnter(paths(container)[0], { clientX: 50, clientY: 40 });
    await fireEvent.mouseLeave(container.querySelector("svg") as SVGElement);
    expect(container.querySelector(".chart-tooltip")).toBeNull();
  });

  it("mentions excluded value only when there is some", () => {
    const { container, rerender } = render(AllocationChart, {
      props: { breakdown: allocation, colors },
    });
    expect(container.querySelector(".excluded-note")).toHaveTextContent(
      "$1,000.00 in excluded symbols (cash / money-market) not shown.",
    );
    return rerender({ breakdown: { ...allocation, excluded_value: 0 } }).then(() => {
      expect(container.querySelector(".excluded-note")).toBeNull();
    });
  });

  it("shows an unassigned note only when there is unassigned value", async () => {
    const { container, rerender } = render(AllocationChart, {
      props: { breakdown: allocation, colors },
    });
    expect(container.querySelector(".unassigned-note")).toBeNull();
    await rerender({ breakdown: allocationWithUnassigned });
    expect(container.querySelector(".unassigned-note")).toHaveTextContent(
      "$500.00 in unassigned securities not shown — assign them in Holdings.",
    );
  });

  it("keeps zero-value categories in the legend without producing NaN paths", () => {
    const zeros = {
      ...allocation,
      categories: allocation.categories.map((c) => ({
        ...c,
        current_value: 0,
        percent_of_included: 0,
      })),
      included_value: 0,
    };
    const { container } = render(AllocationChart, { props: { breakdown: zeros, colors } });
    const rows = Array.from(container.querySelectorAll(".legend-row"));
    expect(rows.map((r) => r.querySelector(".legend-pct")?.textContent)).toEqual([
      "0.0%",
      "0.0%",
      "0.0%",
    ]);
    for (const p of paths(container)) expect(p.getAttribute("d")).not.toContain("NaN");
  });

  it("draws a non-degenerate slice when one category holds 100%", () => {
    const single = {
      categories: [{ category: "US Stocks", current_value: 5000, percent_of_included: 100 }],
      included_value: 5000,
      excluded_value: 0,
      unassigned_value: 0,
      total_value: 5000,
    };
    const { container } = render(AllocationChart, { props: { breakdown: single, colors } });
    const all = paths(container);
    expect(all).toHaveLength(1);

    // An SVG arc whose start and end coincide draws nothing, so the first arc must end elsewhere.
    const d = all[0].getAttribute("d") ?? "";
    const start = /^\s*M\s+(-?[\d.e+-]+)[ ,]+(-?[\d.e+-]+)/.exec(d);
    const arc =
      /A\s+[\d.]+[ ,]+[\d.]+\s+\d+\s+[01][ ,]+[01][ ,]+(-?[\d.e+-]+)[ ,]+(-?[\d.e+-]+)/.exec(d);
    expect(d).not.toContain("NaN");
    expect(start).not.toBeNull();
    expect(arc).not.toBeNull();
    const dist = Math.hypot(
      Number(start![1]) - Number(arc![1]),
      Number(start![2]) - Number(arc![2]),
    );
    expect(dist).toBeGreaterThan(1e-4);
  });
});
