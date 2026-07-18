import { describe, expect, it } from "vitest";

import { Transaction } from "./api";
import { translate } from "./i18n";
import { groupByMonth, monthKey, summarizeBy } from "./transaction-summary";

function transaction(overrides: Partial<Transaction>): Transaction {
  return {
    id: 1,
    transaction_date: "2026-07-17",
    account_id: 1,
    amount: "100.00",
    currency_code: "SEK",
    transaction_type: "expense",
    description: "Test",
    merchant: null,
    category_id: null,
    notes: null,
    source: "manual",
    created_at: "2026-07-17T12:00:00",
    updated_at: "2026-07-17T12:00:00",
    attachment_filename: null,
    attachment_content_type: null,
    attachment_size: null,
    ...overrides,
  };
}

describe("transaction summaries", () => {
  it("provides English and Swedish translations for shared labels", () => {
    expect(translate("en", "transactions")).toBe("Transactions");
    expect(translate("sv", "transactions")).toBe("Transaktioner");
    expect(translate("sv", "reimbursement")).toBe("Återbetalning");
  });

  it("extracts month keys and groups transactions by month", () => {
    const items = [
      transaction({ id: 1, transaction_date: "2026-07-01" }),
      transaction({ id: 2, transaction_date: "2026-06-30" }),
    ];
    expect(monthKey("2026-07-17")).toBe("2026-07");
    expect(Object.keys(groupByMonth(items))).toEqual(["2026-07", "2026-06"]);
  });

  it("summarizes expenses as negative and income/reimbursements as positive", () => {
    const items = [
      transaction({ id: 1, account_id: 1, category_id: 10, amount: "100.00", transaction_type: "expense" }),
      transaction({ id: 2, account_id: 1, category_id: 10, amount: "25.00", transaction_type: "reimbursement" }),
      transaction({ id: 3, account_id: 2, category_id: 20, amount: "500.00", transaction_type: "income" }),
      transaction({ id: 4, account_id: 2, amount: "80.00", transaction_type: "transfer" }),
    ];
    const categories = summarizeBy(items, "category_id", new Map([[10, "Food"], [20, "Salary"]]));
    const accounts = summarizeBy(items, "account_id", new Map([[1, "Everyday"], [2, "Savings"]]));
    expect(categories).toEqual([
      { key: "20:SEK", label: "Salary", amount: 500, currency_code: "SEK" },
      { key: "10:SEK", label: "Food", amount: -75, currency_code: "SEK" },
    ]);
    expect(accounts.find((row) => row.label === "Everyday")?.amount).toBe(-75);
    expect(accounts.find((row) => row.label === "Savings")?.amount).toBe(500);
  });
});
