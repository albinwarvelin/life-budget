import { AccountMonthlyBalance, Transaction } from "./api";
import { monthKey } from "./transaction-summary";

/** Group API balance rows without merging accounts or currencies. */
export function groupMonthlyBalances(rows: AccountMonthlyBalance[]) {
  return rows.reduce<Record<string, AccountMonthlyBalance[]>>((groups, row) => {
    (groups[row.month] ??= []).push(row);
    return groups;
  }, {});
}

/** Select the newest closing balance for each account for the overview cards. */
export function latestAccountBalances(rows: AccountMonthlyBalance[]) {
  const latest = new Map<number, AccountMonthlyBalance>();
  for (const row of [...rows].sort((left, right) => right.month.localeCompare(left.month))) {
    if (!latest.has(row.account_id)) latest.set(row.account_id, row);
  }
  return [...latest.values()].sort((left, right) =>
    left.account_name.localeCompare(right.account_name)
  );
}

/** Keep balance-only gap months visible alongside filtered transaction activity. */
export function overviewMonthKeys(
  transactions: Transaction[],
  balances: AccountMonthlyBalance[],
) {
  return [...new Set([
    ...transactions.map((transaction) => monthKey(transaction.transaction_date)),
    ...balances.map((balance) => balance.month),
  ])].sort().reverse();
}
