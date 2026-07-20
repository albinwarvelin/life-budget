/**
 * Return the visible sign marker for a stored transaction amount.
 * Savings and transfers are stored signed, so their direction must not be
 * replaced by an unsigned-looking generic symbol in the table.
 */
export function transactionAmountPrefix(
  transactionType: "expense" | "income" | "reimbursement" | "savings" | "transfer",
  amount: string,
): string {
  if (transactionType === "expense") return "−";
  if (transactionType === "income" || transactionType === "reimbursement") return "+";
  if (transactionType === "savings") return Number(amount) < 0 ? "−" : "+";
  return "↔";
}
