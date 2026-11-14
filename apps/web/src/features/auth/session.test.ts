import { describe, expect, it } from "vitest";

import { initials, loginHref } from "./session";

describe("initials", () => {
  it.each([
    ["Ada Lovelace", "AL"],
    ["  grace   brewster murray hopper ", "GH"],
    ["Manasa", "MA"],
    ["", "?"],
  ])("%s → %s", (name, expected) => {
    expect(initials(name)).toBe(expected);
  });
});

describe("loginHref", () => {
  it("keeps in-app return paths only", () => {
    expect(loginHref("/app/data")).toBe("/login?next=%2Fapp%2Fdata");
    expect(loginHref("https://evil.example")).toBe("/login");
    expect(loginHref(null)).toBe("/login");
  });
});
