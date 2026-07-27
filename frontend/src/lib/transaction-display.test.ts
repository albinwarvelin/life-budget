import { describe, expect, it } from "vitest";
import {
  transactionAmountMagnitude,
  transactionAmountPrefix,
} from "./transaction-display";

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

  it("does not display two minus signs for negative savings", () => {
    const rendered =
      transactionAmountPrefix("savings", "-50.00") +
      transactionAmountMagnitude("savings", "-50.00");

    expect(rendered).toBe("−50");
    expect(transactionAmountMagnitude("transfer", "-50.00")).toBe("-50.00");
  });
});
