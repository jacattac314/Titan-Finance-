import { describe, expect, it } from "vitest";
import { cn } from "./utils";

describe("cn", () => {
  it("merges and de-duplicates utility classes", () => {
    expect(cn("px-2", "px-4", "text-sm")).toBe("px-4 text-sm");
  });

  it("filters falsy values", () => {
    expect(cn("hidden", false && "block", undefined, "md:block")).toBe("hidden md:block");
  });
});
