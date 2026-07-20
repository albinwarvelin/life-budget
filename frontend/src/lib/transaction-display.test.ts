import { describe, expect, it } from "vitest";
import { transactionAmountPrefix } from "./transaction-display";

describe("transactionAmountPrefix", () => {
  it("preserves the direction of savings amounts", () => {
    expect(transactionAmountPrefix("savings", "50.00")).toBe("+");
    expect(transactionAmountPrefix("savings", "-50.00")).toBe("−");
  });

  it("uses the established markers for other transaction types", () => {
    expect(transactionAmountPrefix("expense", "10.00")).toBe("−");
    expect(transactionAmountPrefix("income", "10.00")).toBe("+");
    expect(transactionAmountPrefix("transfer", "10.00")).toBe("↔");
  });
});
