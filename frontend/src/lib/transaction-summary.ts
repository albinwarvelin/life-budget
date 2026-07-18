import { Transaction } from "./api";

export type SummaryRow = { key: string; label: string; amount: number; currency_code: string };
export function monthKey(date: string) { return date.slice(0, 7); }
export function groupByMonth(transactions: Transaction[]) {
  return transactions.reduce<Record<string, Transaction[]>>((groups, transaction) => {
    const key = monthKey(transaction.transaction_date);
    (groups[key] ??= []).push(transaction);
    return groups;
  }, {});
}
export function summarizeBy(transactions: Transaction[], key: "account_id" | "category_id", labels: Map<number, string>): SummaryRow[] {
  const rows = new Map<string, SummaryRow>();
  for (const transaction of transactions) {
    if (transaction.transaction_type === "transfer") continue;
    const id = transaction[key];
    // The currency is part of the grouping key: SEK and NOK must never be
    // silently added together in an account/category summary.
    const rowKey = `${id === null ? "none" : String(id)}:${transaction.currency_code}`;
    const existing = rows.get(rowKey) ?? { key: rowKey, label: id === null ? "Uncategorized" : labels.get(id) ?? "Unknown", amount: 0, currency_code: transaction.currency_code };
    existing.amount += Number(transaction.amount) * (transaction.transaction_type === "expense" ? -1 : 1);
    rows.set(rowKey, existing);
  }
  return [...rows.values()].sort((a, b) => Math.abs(b.amount) - Math.abs(a.amount));
}
