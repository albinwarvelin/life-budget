import { describe, expect, it } from "vitest";

import { Transaction } from "../lib/api";
import { accountBalances, totals } from "./App";

function transaction(overrides: Partial<Transaction>): Transaction {
  return {
    id: 1,
    transaction_date: "2026-07-01",
    account_id: 1,
    amount: "100.00",
    currency_code: "SEK",
    transaction_type: "income",
    description: null,
    merchant: "Test",
    category_id: null,
    notes: null,
    source: "manual",
    created_at: "2026-07-01T12:00:00",
    updated_at: "2026-07-01T12:00:00",
    attachment_filename: null,
    attachment_content_type: null,
    attachment_size: null,
    ...overrides,
  };
}

describe("transfer totals and balances", () => {
  it("includes signed transfers in the monthly net total", () => {
    const result = totals([
      transaction({ amount: "150.00", transaction_type: "transfer" }),
      transaction({ id: 2, amount: "-40.00", transaction_type: "transfer" }),
    ]);

    expect(result.transfer.SEK).toBe(110);
    expect(result.net.SEK).toBe(110);
  });

  it("applies the signed transfer amount to the owning account balance", () => {
    const balances = accountBalances(
      [
        transaction({ account_id: 1, amount: "150.00", transaction_type: "transfer" }),
        transaction({ id: 2, account_id: 2, amount: "-40.00", transaction_type: "transfer" }),
      ],
      new Map([
        [1, "Everyday"],
        [2, "Savings"],
      ]),
    );

    expect(balances.find((item) => item.label === "Everyday")?.values.SEK).toBe(150);
    expect(balances.find((item) => item.label === "Savings")?.values.SEK).toBe(-40);
  });
});
