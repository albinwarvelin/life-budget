import { describe, expect, it } from "vitest";

import { Transaction } from "./api";
import { translate } from "./i18n";
import { groupByMonth, monthKey } from "./transaction-summary";

function transaction(overrides: Partial<Transaction>): Transaction {
  return {
    id: 1,
    transaction_date: "2026-07-17",
    account_id: 1,
    amount: "100.00",
    currency_code: "SEK",
    transaction_type: "expense",
    description: "Test",
    merchant: "Test merchant",
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
});
