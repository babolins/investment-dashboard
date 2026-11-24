import { describe, expect, it } from "vitest";
import {
  duplicateName,
  parseTarget,
  validateName,
  validateSymbol,
  validateTarget,
} from "./categoryValidation";
import { groupedConfig } from "../test/fixtures";

describe("validateName", () => {
  it("accepts an ordinary name", () => {
    expect(validateName("Gold", "category")).toBeNull();
  });

  it.each([
    ["", /enter a group name/i],
    ["x".repeat(41), /at most 40/],
    ["a/b", /"\/"/],
    ["Unassigned", /reserved/],
    ["EXCLUDED", /reserved/],
  ])("rejects %j", (name, message) => {
    expect(validateName(name, "group")).toMatch(message);
  });

  it("allows exactly 40 characters", () => {
    expect(validateName("x".repeat(40), "group")).toBeNull();
  });
});

describe("validateSymbol", () => {
  it.each(["VTI", "BRK.B", "A-B", "ABCDEFGHIJ"])("accepts %s", (s) => {
    expect(validateSymbol(s)).toBeNull();
  });
  it.each(["", "vti", "not a symbol", "ABCDEFGHIJK"])("rejects %j", (s) => {
    expect(validateSymbol(s)).not.toBeNull();
  });
});

describe("validateTarget", () => {
  it.each([null, 0, 50.5, 100])("accepts %s", (t) => {
    expect(validateTarget(t)).toBeNull();
  });
  it.each([-1, 100.1, NaN])("rejects %s", (t) => {
    expect(validateTarget(t)).not.toBeNull();
  });
});

describe("duplicateName", () => {
  it("matches groups and categories case-insensitively", () => {
    expect(duplicateName(groupedConfig, "stocks")).toMatch(/already exists/);
    expect(duplicateName(groupedConfig, "BONDS")).toMatch(/already exists/);
    expect(duplicateName(groupedConfig, "Gold")).toBeNull();
  });
});

describe("parseTarget", () => {
  it("maps empty input to null and coerces the rest", () => {
    expect(parseTarget(null)).toBeNull();
    expect(parseTarget("")).toBeNull();
    expect(parseTarget("12.5")).toBe(12.5);
    expect(parseTarget(0)).toBe(0);
  });
});
