import { describe, expect, it } from "vitest";
import { config } from "../test/fixtures";
import {
  BUCKET_COLORS,
  BUCKETS,
  FALLBACK_COLOR,
  bucketBadgeClass,
  bucketColor,
  bucketLabelBySymbol,
  symbolsByBucket,
} from "./buckets";

describe("BUCKETS", () => {
  it("lists the three buckets in display order", () => {
    expect([...BUCKETS]).toEqual(["VTI", "VXUS", "BND"]);
  });
});

describe("bucketColor", () => {
  it.each([
    ["VTI", "#1B3A6B"],
    ["VXUS", "#4AACE8"],
    ["BND", "#6B7A23"],
  ])("returns the brand colour for %s", (bucket, color) => {
    expect(bucketColor(bucket)).toBe(color);
    expect(BUCKET_COLORS[bucket]).toBe(color);
  });

  it("falls back to grey for unknown buckets", () => {
    expect(FALLBACK_COLOR).toBe("#999");
    expect(bucketColor("GOLD")).toBe(FALLBACK_COLOR);
  });
});

describe("symbolsByBucket", () => {
  it("lists every symbol feeding each bucket, including fractional ones", () => {
    expect(symbolsByBucket(config)).toEqual({
      VTI: ["FZROX", "ITOT", "VTI"],
      VXUS: ["FZROX", "VXUS"],
      BND: ["BND"],
    });
  });

  it("returns an empty object without a config", () => {
    expect(symbolsByBucket(null)).toEqual({});
  });
});

describe("bucketLabelBySymbol", () => {
  it("labels symbols by bucket, joining fractional buckets and marking exclusions", () => {
    expect(bucketLabelBySymbol(config)).toEqual({
      VTI: "VTI",
      VXUS: "VXUS",
      BND: "BND",
      ITOT: "VTI",
      FZROX: "VTI/VXUS",
      SPAXX: "Excl.",
    });
  });

  it("returns an empty object without a config", () => {
    expect(bucketLabelBySymbol(null)).toEqual({});
  });
});

describe("bucketBadgeClass", () => {
  it.each([
    ["VTI", "bucket-badge bucket-badge--vti"],
    ["VTI/VXUS", "bucket-badge bucket-badge--vti-vxus"],
    ["BND/VTI/VXUS", "bucket-badge bucket-badge--bnd-vti-vxus"],
    ["Excl.", "bucket-badge bucket-badge--excl"],
  ])("maps %j to a modifier class", (label, expected) => {
    expect(bucketBadgeClass(label)).toBe(expected);
  });

  it.each([[undefined], [""]])("has no modifier for %j", (label) => {
    expect(bucketBadgeClass(label)).toBe("bucket-badge");
  });
});
