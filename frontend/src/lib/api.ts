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
export type AccountMonthlyBalance = {
  month: string;
  account_id: number;
  account_name: string;
  currency_code: string;
  carried_over: string;
  monthly_change: string;
  ending_balance: string;
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

export type LearningModelKind = "category" | "type" | "description";
export type PredictionOutput = {
  suggestion: string | null;
  confidence: number;
  calibrated: boolean;
  context_weight?: number;
  reason: string;
  candidates: { key: string; label: string; probability: number; support: number;
    contributions: { feature: string; contribution: number }[] }[];
};
export type PredictionResult = {
  snapshot_id: number;
  outputs: Record<LearningModelKind, PredictionOutput>;
};
export type EvaluationMetrics = {
  samples: number;
  accuracy: number | null;
  macro_f1: number | null;
  log_loss: number | null;
  baseline_accuracy?: number;
  top_three_accuracy?: number;
  coverage?: number;
  suggestion_precision?: number | null;
  unseen_counterparties?: number;
  calibration_bins?: { score: number; accuracy: number; count: number }[];
};
export type LearningModelStatus = {
  reviewed_transactions: number;
  pending_updates: number;
  updates_since_training: number;
  needs_retraining: boolean;
  snapshot_id: number | null;
  dataset_revision: number;
  algorithm: string | null;
  created_at: string | null;
  heads: Record<LearningModelKind, {
    labels: number; calibrated: boolean; threshold: number;
    regularization: number; temperature: number;
  }>;
  configuration: {
    regularization_candidates: number[]; temperature_candidates: number[];
    threshold_candidates: number[]; minimum_support: number;
    suggestion_thresholds: Partial<Record<LearningModelKind, number>>;
    description_blend_candidates: number[]; description_context_min_rows: number;
    minimum_validation_samples: number; target_precision: number; wilson_z: number;
    train_fraction: number; validation_fraction: number;
    word_ngram_range: [number, number]; character_ngram_range: [number, number];
    word_features: number; character_features: number; amount_centers: number; amount_width: number;
  };
  report: {
    chronological: Record<LearningModelKind, EvaluationMetrics>;
    unseen_counterparty: Record<LearningModelKind, EvaluationMetrics> | null;
    training_samples: number;
    validation_samples: number;
    test_samples: number;
    description_context: string;
    description_context_reason: string;
    description_context_selection?: {
      weight: number; validation_base_log_loss: number | null; validation_blend_log_loss: number | null;
    };
    description_comparison?: { independent: EvaluationMetrics; blended: EvaluationMetrics };
  } | null;
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

type ApiValidationIssue = {
  loc?: unknown[];
  msg?: unknown;
};

/** Turn FastAPI strings and structured validation issues into readable UI text. */
export function formatApiError(detail: unknown, status: number): string {
  if (typeof detail === "string" && detail.trim()) return detail;

  if (Array.isArray(detail)) {
    const messages = detail
      .map((issue) => formatValidationIssue(issue))
      .filter((message): message is string => Boolean(message));
    if (messages.length) return messages.join(" · ");
  }

  // Some endpoints may return a structured domain error instead of FastAPI's
  // validation list. Prefer its message, but never stringify an object into
  // the unhelpful "[object Object]" text previously shown by the import UI.
  if (detail && typeof detail === "object" && "message" in detail) {
    const message = (detail as { message?: unknown }).message;
    if (typeof message === "string" && message.trim()) return message;
  }
  return `Request failed (${status})`;
}

function formatValidationIssue(value: unknown): string | null {
  if (!value || typeof value !== "object") return null;
  const issue = value as ApiValidationIssue;
  if (typeof issue.msg !== "string") return null;

  const location = Array.isArray(issue.loc)
    ? issue.loc.filter((part) => part !== "body")
    : [];
  const rowPosition = location[0] === "rows" && typeof location[1] === "number"
    ? location[1] + 1
    : null;
  const fieldParts = location.slice(rowPosition === null ? 0 : 2)
    .filter((part): part is string | number => ["string", "number"].includes(typeof part))
    .map((part) => String(part).replaceAll("_", " "));
  const prefix = [
    rowPosition === null ? null : `Row ${rowPosition}`,
    fieldParts.length ? fieldParts.join(" ") : null,
  ].filter(Boolean).join(" · ");
  return prefix ? `${prefix}: ${issue.msg}` : issue.msg;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const isFormData = options?.body instanceof FormData;
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: isFormData
      ? options?.headers
      : { "Content-Type": "application/json", ...(options?.headers ?? {}) },
    ...options,
  });

  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: unknown } | null;
    throw new Error(formatApiError(body?.detail, response.status));
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  listCurrencies: () => request<Currency[]>("/api/v1/currencies"),
  listAccounts: () => request<Account[]>("/api/v1/accounts"),
  listAccountMonthlyBalances: (params: URLSearchParams) =>
    request<AccountMonthlyBalance[]>(`/api/v1/account-monthly-balances?${params.toString()}`),
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
  getLearningModelStatus: () => request<LearningModelStatus>("/api/v1/learning-models/status"),
  retrainLearningModels: () => request<LearningModelStatus>("/api/v1/learning-models/retrain", { method: "POST" }),
  testPrediction: (input: { merchant: string; amount: string; currency_code: string; account_id?: number }) =>
    request<PredictionResult>("/api/v1/learning-models/predict", {
      method: "POST", body: JSON.stringify(input),
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
