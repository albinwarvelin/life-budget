import { describe, expect, it } from "vitest";

import { formatApiError } from "./api";

describe("API error formatting", () => {
  it("keeps plain domain error messages", () => {
    expect(formatApiError("Account not found", 400)).toBe("Account not found");
  });

  it("names the import row and field for FastAPI validation errors", () => {
    const detail = [
      {
        type: "string_too_short",
        loc: ["body", "rows", 1, "merchant"],
        msg: "String should have at least 1 character",
      },
      {
        type: "decimal_parsing",
        loc: ["body", "rows", 2, "signed_amount"],
        msg: "Input should be a valid decimal",
      },
    ];

    expect(formatApiError(detail, 422)).toBe(
      "Row 2 · merchant: String should have at least 1 character · " +
      "Row 3 · signed amount: Input should be a valid decimal",
    );
  });

  it("never renders an unknown object as object Object", () => {
    const message = formatApiError({ unexpected: true }, 500);
    expect(message).toBe("Request failed (500)");
    expect(message).not.toContain("[object Object]");
  });
});
