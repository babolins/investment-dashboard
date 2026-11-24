import { render, screen } from "@testing-library/svelte";
import { describe, expect, it } from "vitest";
import BuyGuidance from "./BuyGuidance.svelte";
import { rebalance } from "../test/fixtures";

describe("BuyGuidance", () => {
  it("shows the heading and the total to invest", () => {
    render(BuyGuidance, { props: { result: rebalance } });
    expect(screen.getByRole("heading", { name: "Buy Guidance" })).toBeInTheDocument();
    expect(screen.getByText("$1,000.00").tagName).toBe("STRONG");
  });

  it("renders a row per recommendation with amount, share and current/target", () => {
    const { container } = render(BuyGuidance, { props: { result: rebalance } });
    const rows = Array.from(container.querySelectorAll(".guidance-row"));
    expect(rows).toHaveLength(3);

    const [vti, vxus, bnd] = rows;
    expect(vti.querySelector("strong")).toHaveTextContent("VTI");
    expect(vti.querySelector(".buy-dollars")).toHaveTextContent("$0.00");
    expect(vti.querySelector(".buy-pct")).toHaveTextContent("0.0% of investment");
    expect(vti.querySelector(".guidance-context")).toHaveTextContent("Current: 60.0%");
    expect(vti.querySelector(".guidance-context")).toHaveTextContent("Target: 48.0%");

    expect(vxus.querySelector("strong")).toHaveTextContent("VXUS");
    expect(vxus.querySelector(".buy-dollars")).toHaveTextContent("$302.33");
    expect(vxus.querySelector(".buy-pct")).toHaveTextContent("30.2% of investment");
    expect(vxus.querySelector(".guidance-bar")).toHaveStyle({ background: "#4AACE8" });

    expect(bnd.querySelector(".buy-dollars")).toHaveTextContent("$697.67");
    expect(bnd.querySelector(".buy-pct")).toHaveTextContent("69.8% of investment");
    expect(bnd.querySelector(".guidance-context")).toHaveTextContent("Current: 10.0%");
    expect(bnd.querySelector(".guidance-context")).toHaveTextContent("Target: 20.0%");
    expect((bnd.querySelector(".guidance-bar") as HTMLElement).style.width).toBe("69.8%");
  });

  it("shows the post-trade allocation with target markers", () => {
    const { container } = render(BuyGuidance, { props: { result: rebalance } });
    const rows = Array.from(container.querySelectorAll(".post-trade-row"));
    expect(rows).toHaveLength(3);

    expect(rows.map((r) => r.querySelector(".post-trade-pct")?.textContent)).toEqual([
      "54.5%",
      "30.0%",
      "15.4%",
    ]);
    expect(rows.map((r) => r.querySelector(".post-trade-target")?.textContent)).toEqual([
      "target 48.0%",
      "target 32.0%",
      "target 20.0%",
    ]);
    expect((rows[0].querySelector(".post-trade-bar") as HTMLElement).style.width).toBe("54.5%");
    expect(rows[1].querySelector(".post-trade-bar")).toHaveStyle({ background: "#4AACE8" });
    const marker = rows[2].querySelector(".post-trade-target-line") as HTMLElement;
    expect(marker.style.left).toBe("20%"); // jsdom normalises "20.0%" to "20%"
    expect(marker).toHaveAttribute("title", "Target: 20.0%");
  });

  it("never shows a rounding note, even when totals differ", () => {
    render(BuyGuidance, { props: { result: { ...rebalance, total_buy_amount: 990 } } });
    expect(screen.queryByText(/rounding/i)).toBeNull();
  });

  it("copes with no recommendations", () => {
    const { container } = render(BuyGuidance, {
      props: { result: { recommendations: [], investment_amount: 1000, total_buy_amount: 0 } },
    });
    expect(container.querySelectorAll(".guidance-row")).toHaveLength(0);
    expect(container.textContent).not.toContain("NaN");
  });
});
