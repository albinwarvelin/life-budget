import { Transaction } from "./api";

export function monthKey(date: string) { return date.slice(0, 7); }
export function groupByMonth(transactions: Transaction[]) {
  return transactions.reduce<Record<string, Transaction[]>>((groups, transaction) => {
    const key = monthKey(transaction.transaction_date);
    (groups[key] ??= []).push(transaction);
    return groups;
  }, {});
}
