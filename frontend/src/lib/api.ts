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
  localized_names: Record<string, string>;
  kind: "expense" | "income" | "reimbursement" | "savings";
  parent_id: number | null;
  is_active: boolean;
};
export type Transaction = {
  id: number;
  transaction_date: string;
  account_id: number;
  amount: string;
  currency_code: string;
  transaction_type: "expense" | "income" | "reimbursement" | "savings" | "transfer";
  description: string | null;
  merchant: string;
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
  description?: string;
  merchant: string;
  category_id?: number | null;
  notes?: string;
  source?: string;
};

export type CategoryPrediction = {
  category_id: number;
  confidence: number;
  reason: string;
};

export type LearningPattern = {
  id: number;
  pattern_type: string;
  pattern_text: string;
  category_id: number;
  account_id: number | null;
  transaction_type: Transaction["transaction_type"] | null;
  weight: number;
  observations: number;
};

export type LearningModel = {
  categories: Pick<Category, "id" | "name" | "localized_names" | "kind">[];
  patterns: LearningPattern[];
  event_count: number;
  scoring: {
    signal_weights: Record<string, number>;
    account_multiplier: number;
    similarity_threshold: number;
  };
};

export type LearningModelKind = "category" | "type" | "description";
export type ExplorerPattern = {
  id: number;
  pattern_type: string;
  pattern_text: string;
  display_text: string | null;
  localized_display_texts: Record<string, string>;
  target_key: string;
  weight: number;
  observations: number;
  account_id: number | null;
  transaction_type: Transaction["transaction_type"] | null;
  category_id: number | null;
};
export type ExplorerModel = {
  model_kind: LearningModelKind;
  targets: { key: string; label: string; localized_names: Record<string, string> }[];
  patterns: ExplorerPattern[];
  event_count: number;
  scoring: {
    signal_weights: Record<string, number>;
    similarity_threshold: number;
    account_multiplier: number | null;
    minimum_confidence: number | null;
  };
};

export type DescriptionPredictionContribution = {
  signal_type: string;
  signal_value: string;
  matched_value: string;
  description: string;
  observations: number;
  conditional_probability: number;
  baseline_probability: number;
  reliability: number;
  similarity: number;
  contribution: number;
};

export type DescriptionPredictionResult = {
  description: string | null;
  confidence: number;
  reason: string;
  candidates: {
    description: string;
    score: number;
    relative_score: number;
    contributions: DescriptionPredictionContribution[];
  }[];
};

export type ImportDraft = {
  id: number;
  row_index: number;
  raw_text: string;
  raw_amount_text: string | null;
  source_bounds: Record<string, number> | null;
  transaction_date: string | null;
  merchant: string | null;
  description: string | null;
  predicted_description: string | null;
  signed_amount: string | null;
  currency_code: string;
  account_id: number;
  predicted_category_id: number | null;
  predicted_transaction_type: Transaction["transaction_type"] | null;
  category_confidence: number;
  type_confidence: number;
  description_confidence: number;
  extraction_confidence: number;
  validation_errors: string[];
  possible_duplicate: boolean;
  status: string;
};

export type ImportBatch = {
  id: number;
  original_filename: string;
  content_type: string;
  account_id: number;
  currency_code: string;
  status: "queued" | "processing" | "review" | "completed" | "error";
  progress: number;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  drafts: ImportDraft[];
};

export type ApprovedImportRow = {
  draft_id: number;
  accepted: boolean;
  transaction_date: string;
  merchant: string;
  description?: string;
  signed_amount: string;
  currency_code: string;
  account_id: number;
  transaction_type: Transaction["transaction_type"];
  category_id: number | null;
  notes?: string;
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
  updateAccount: (id: number, input: AccountInput) =>
    request<Account>(`/api/v1/accounts/${id}`, {
      method: "PUT",
      body: JSON.stringify(input),
    }),
  deleteAccount: (id: number) =>
    request<void>(`/api/v1/accounts/${id}`, { method: "DELETE" }),
  listCategories: () => request<Category[]>("/api/v1/categories"),
  getLearningModel: () =>
    request<LearningModel>("/api/v1/category-learning/model"),
  getExplorerModel: (kind: LearningModelKind) =>
    request<ExplorerModel>(`/api/v1/learning-models/${kind}`),
  testDescriptionPrediction: (input: {
    merchant: string;
    amount: string;
    currency_code: string;
    category_id?: number;
    transaction_type?: Transaction["transaction_type"];
  }) =>
    request<DescriptionPredictionResult>("/api/v1/learning-models/description/predict", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  suggestCategories: (input: {
    merchant: string;
    description?: string;
    account_id?: number;
    transaction_type?: Transaction["transaction_type"];
    amount?: string;
    currency_code?: string;
  }) =>
    request<CategoryPrediction[]>("/api/v1/category-suggestions", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  createCategory: (input: { name: string; kind: Category["kind"]; parent_id?: number | null; localized_names?: Record<string, string> }) =>
    request<Category>("/api/v1/categories", { method: "POST", body: JSON.stringify(input) }),
  updateCategory: (id: number, input: { name: string; kind: Category["kind"]; parent_id?: number | null; localized_names?: Record<string, string> }) =>
    request<Category>(`/api/v1/categories/${id}`, { method: "PUT", body: JSON.stringify(input) }),
  deleteCategory: (id: number) =>
    request<void>(`/api/v1/categories/${id}`, { method: "DELETE" }),
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
  uploadScreenshot: (file: File, accountId: number) => {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("account_id", String(accountId));
    return request<ImportBatch>("/api/v1/imports/screenshots", {
      method: "POST",
      body: formData,
    });
  },
  getImportBatch: (id: number) => request<ImportBatch>(`/api/v1/imports/${id}`),
  approveImport: (id: number, rows: ApprovedImportRow[]) =>
    request<{ batch_id: number; created_transaction_ids: number[]; rejected_draft_ids: number[] }>(
      `/api/v1/imports/${id}/approve`,
      { method: "POST", body: JSON.stringify({ rows }) },
    ),
  importImageUrl: (id: number) => `${API_BASE_URL}/api/v1/imports/${id}/image`,
};
