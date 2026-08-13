import { describe, expect, it } from "vitest";

import { AccountMonthlyBalance, Transaction } from "./api";
import {
  groupMonthlyBalances,
  latestAccountBalances,
  overviewMonthKeys,
} from "./monthly-balances";

const rows: AccountMonthlyBalance[] = [
  {
    month: "2026-02", account_id: 1, account_name: "Everyday", currency_code: "SEK",
    carried_over: "100.00", monthly_change: "0.00", ending_balance: "100.00",
  },
  {
    month: "2026-01", account_id: 1, account_name: "Everyday", currency_code: "SEK",
    carried_over: "0.00", monthly_change: "100.00", ending_balance: "100.00",
  },
  {
    month: "2026-02", account_id: 2, account_name: "Norway", currency_code: "NOK",
    carried_over: "0.00", monthly_change: "50.00", ending_balance: "50.00",
  },
];

describe("monthly balance overview mapping", () => {
  it("groups rows by month without combining currencies", () => {
    const grouped = groupMonthlyBalances(rows);
    expect(grouped["2026-02"]).toHaveLength(2);
    expect(grouped["2026-02"].map((row) => row.currency_code)).toEqual(["SEK", "NOK"]);
  });

  it("uses each account's newest closing balance for the summary cards", () => {
    expect(latestAccountBalances([...rows].reverse())).toEqual([rows[0], rows[2]]);
  });

  it("retains balance-only gap months when activity is filtered", () => {
    const transaction = {
      transaction_date: "2026-03-01",
    } as Transaction;
    expect(overviewMonthKeys([transaction], rows)).toEqual([
      "2026-03",
      "2026-02",
      "2026-01",
    ]);
  });
});
