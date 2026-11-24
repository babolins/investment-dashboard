import { fireEvent, render, screen } from "@testing-library/svelte";
import { describe, expect, it } from "vitest";
import AllocationChart from "./AllocationChart.svelte";
import { allocation } from "../test/fixtures";

const bucketSymbols = { VTI: ["FZROX", "ITOT", "VTI"], VXUS: ["FZROX", "VXUS"], BND: ["BND"] };

// The donut and its mouse handlers are presentational; the legend carries the information.
function paths(container: HTMLElement) {
  return Array.from(container.querySelectorAll("path"));
}

describe("AllocationChart", () => {
  it("shows the heading and the included value", () => {
    render(AllocationChart, { props: { breakdown: allocation } });
    expect(screen.getByRole("heading", { name: "Asset Allocation" })).toBeInTheDocument();
    expect(screen.getByText(/included value \$10,000\.00/)).toBeInTheDocument();
  });

  it("draws one path per bucket, in order, filled with the bucket colour", () => {
    const { container } = render(AllocationChart, { props: { breakdown: allocation } });
    expect(paths(container).map((p) => p.getAttribute("fill"))).toEqual([
      "#6B7A23", // BND
      "#1B3A6B", // VTI
      "#4AACE8", // VXUS
    ]);
  });

  it("renders a legend row per bucket with its percentage to 1 dp", () => {
    const { container } = render(AllocationChart, { props: { breakdown: allocation } });
    const rows = Array.from(container.querySelectorAll(".legend-row"));
    expect(rows.map((r) => r.querySelector(".legend-label")?.textContent)).toEqual([
      "BND",
      "VTI",
      "VXUS",
    ]);
    expect(rows.map((r) => r.querySelector(".legend-pct")?.textContent)).toEqual([
      "10.0%",
      "60.0%",
      "30.0%",
    ]);
    expect(rows[1].querySelector(".legend-dot")).toHaveStyle({ background: "#1B3A6B" });
  });

  it("shows no tooltip until a slice is hovered", () => {
    const { container } = render(AllocationChart, { props: { breakdown: allocation } });
    expect(container.querySelector(".chart-tooltip")).toBeNull();
  });

  it("shows bucket, value, percentage and tickers when hovering a slice", async () => {
    const { container } = render(AllocationChart, {
      props: { breakdown: allocation, bucketSymbols },
    });
    await fireEvent.mouseEnter(paths(container)[1], { clientX: 50, clientY: 40 });

    const tip = container.querySelector(".chart-tooltip") as HTMLElement;
    expect(tip).toBeInTheDocument();
    expect(tip.querySelector("strong")).toHaveTextContent("VTI");
    expect(tip).toHaveTextContent("$6,000.00");
    expect(tip).toHaveTextContent("60.0%");
    expect(tip.querySelector(".tooltip-tickers")).toHaveTextContent("FZROX, ITOT, VTI");
  });

  it("omits the tickers line when the bucket has no tickers", async () => {
    const { container } = render(AllocationChart, { props: { breakdown: allocation } });
    await fireEvent.mouseEnter(paths(container)[0], { clientX: 50, clientY: 40 });
    expect(container.querySelector(".chart-tooltip")).toBeInTheDocument();
    expect(container.querySelector(".tooltip-tickers")).toBeNull();
  });

  it("switches the tooltip content when hovering another slice", async () => {
    const { container } = render(AllocationChart, {
      props: { breakdown: allocation, bucketSymbols },
    });
    await fireEvent.mouseEnter(paths(container)[1], { clientX: 50, clientY: 40 });
    await fireEvent.mouseEnter(paths(container)[2], { clientX: 60, clientY: 40 });
    const tip = container.querySelector(".chart-tooltip") as HTMLElement;
    expect(tip.querySelector("strong")).toHaveTextContent("VXUS");
    expect(tip).toHaveTextContent("$3,000.00");
  });

  it("hides the tooltip when the pointer leaves the chart", async () => {
    const { container } = render(AllocationChart, { props: { breakdown: allocation } });
    await fireEvent.mouseEnter(paths(container)[0], { clientX: 50, clientY: 40 });
    await fireEvent.mouseLeave(container.querySelector("svg") as SVGElement);
    expect(container.querySelector(".chart-tooltip")).toBeNull();
  });

  it("mentions excluded value only when there is some", () => {
    const { container, rerender } = render(AllocationChart, { props: { breakdown: allocation } });
    expect(container.querySelector(".excluded-note")).toHaveTextContent(
      "$1,000.00 in excluded symbols (cash / money-market) not shown.",
    );
    return rerender({ breakdown: { ...allocation, excluded_value: 0 } }).then(() => {
      expect(container.querySelector(".excluded-note")).toBeNull();
    });
  });

  it("draws a non-degenerate slice when one bucket holds 100%", () => {
    const single = {
      buckets: [{ bucket: "VTI" as const, current_value: 5000, percent_of_included: 100 }],
      included_value: 5000,
      excluded_value: 0,
      total_value: 5000,
    };
    const { container } = render(AllocationChart, { props: { breakdown: single } });
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
