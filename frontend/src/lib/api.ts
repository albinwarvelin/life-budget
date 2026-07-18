// The frontend talks to the FastAPI backend through this small typed client.
// Keeping fetch calls here prevents components from knowing URL construction
// and gives us one place to turn backend errors into useful messages.

// An empty default uses Vite's /api proxy, avoiding CORS during local development.
const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "").replace(
  /\/$/,
  "",
);

export type Currency = { code: string; name: string };
export type Account = {
  id: number;
  name: string;
  account_type: string;
  currency_code: string;
  institution: string | null;
  is_active: boolean;
};
export type Category = {
  id: number;
  name: string;
  kind: "expense" | "income" | "reimbursement";
  parent_id: number | null;
  is_active: boolean;
};
export type Transaction = {
  id: number;
  transaction_date: string;
  account_id: number;
  amount: string;
  currency_code: string;
  transaction_type: "expense" | "income" | "reimbursement" | "transfer";
  description: string;
  merchant: string | null;
  category_id: number | null;
  notes: string | null;
  source: string;
  created_at: string;
  updated_at: string;
  attachment_filename: string | null;
  attachment_content_type: string | null;
  attachment_size: number | null;
};

export type AccountInput = {
  name: string;
  account_type: string;
  currency_code: string;
  institution?: string;
};

export type TransactionInput = {
  transaction_date: string;
  account_id: number;
  amount: string;
  currency_code: string;
  transaction_type: Transaction["transaction_type"];
  description: string;
  merchant?: string;
  category_id?: number | null;
  notes?: string;
  source?: string;
};

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const isFormData = options?.body instanceof FormData;
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: isFormData
      ? options?.headers
      : { "Content-Type": "application/json", ...(options?.headers ?? {}) },
    ...options,
  });

  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(body?.detail ?? `Request failed (${response.status})`);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  listCurrencies: () => request<Currency[]>("/api/v1/currencies"),
  listAccounts: () => request<Account[]>("/api/v1/accounts"),
  createAccount: (input: AccountInput) =>
    request<Account>("/api/v1/accounts", { method: "POST", body: JSON.stringify(input) }),
  listCategories: () => request<Category[]>("/api/v1/categories"),
  listTransactions: (params: URLSearchParams) =>
    request<Transaction[]>(`/api/v1/transactions?${params.toString()}`),
  createTransaction: (input: TransactionInput) =>
    request<Transaction>("/api/v1/transactions", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  updateTransaction: (id: number, input: TransactionInput) =>
    request<Transaction>(`/api/v1/transactions/${id}`, {
      method: "PUT",
      body: JSON.stringify(input),
    }),
  deleteTransaction: (id: number) =>
    request<void>(`/api/v1/transactions/${id}`, { method: "DELETE" }),
  uploadAttachment: (id: number, file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return request<Transaction>(`/api/v1/transactions/${id}/attachment`, {
      method: "POST",
      body: formData,
    });
  },
  deleteAttachment: (id: number) =>
    request<void>(`/api/v1/transactions/${id}/attachment`, { method: "DELETE" }),
};
