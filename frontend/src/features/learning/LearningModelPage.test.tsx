import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LearningModelStatus } from "../../lib/api";
import { LearningModelPage } from "./LearningModelPage";

// Synthetic API state checks the page's contract without a browser dependency
// or any real ledger data. Model fetching and training are never exercised here.
const query = vi.hoisted(() => ({ state: {} as Record<string, unknown>, refetch: vi.fn(), mutation: {} as Record<string, unknown> }));
vi.mock("@tanstack/react-query", () => ({
  useQuery: ({ queryKey }: { queryKey: string[] }) => queryKey[0] === "learning-model-status"
    ? { ...query.state, refetch: query.refetch }
    : { data: [] },
  useMutation: () => ({ isPending: false, mutate: vi.fn(), ...query.mutation }),
  useQueryClient: () => ({ setQueryData: vi.fn() }),
}));
vi.mock("../../lib/i18n", () => ({ useI18n: () => ({ locale: "en" }) }));

function renderPage() {
  return renderToStaticMarkup(<MemoryRouter><LearningModelPage /></MemoryRouter>);
}

describe("experimental model lab", () => {
  beforeEach(() => { query.state = {}; query.mutation = {}; });

  it("keeps the explanation available while reporting a loading status", () => {
    query.state = { isPending: true, isFetching: true };
    const html = renderPage();
    expect(html).toContain('role="status"');
    expect(html).toContain("Loading the current model");
    expect(html).toContain("Synthetic experiment");
    expect(html).not.toContain("Active snapshot");
  });

  it("shows an actionable fetch error alongside the experiment", () => {
    query.state = { isError: true, error: new Error("Model unavailable") };
    const html = renderPage();
    expect(html).toContain('role="alert"');
    expect(html).toContain("Model unavailable");
    expect(html).toContain("Refresh status");
    expect(html).toContain("Test a transaction");
  });

  it("distinguishes disabled suggestions from fitted parameters and displays API policy", () => {
    const head = { labels: 4, calibrated: true, threshold: 0.9, regularization: 4, temperature: 1.5 };
    const emptyMetrics = { samples: 0, accuracy: null, macro_f1: null, log_loss: null };
    const status: LearningModelStatus = {
      reviewed_transactions: 60, pending_updates: 2, snapshot_id: 7, dataset_revision: 9,
      updates_since_training: 2, needs_retraining: true,
      algorithm: "synthetic-v1", created_at: "2026-01-01T12:00:00Z",
      heads: { type: head, category: head, description: { ...head, threshold: 1.1 } },
      configuration: {
        regularization_candidates: [0.25, 1, 4], temperature_candidates: [0.75, 1, 1.5, 2],
        threshold_candidates: [0.5, 0.9], minimum_support: 6, minimum_validation_samples: 20,
        suggestion_thresholds: { category: 0.75, description: 0.75 }, description_blend_candidates: [0, 0.25, 0.5], description_context_min_rows: 20,
        target_precision: 0.8, wilson_z: 1.96, train_fraction: 0.6, validation_fraction: 0.2,
        word_ngram_range: [1, 2], character_ngram_range: [3, 5], word_features: 2000,
        character_features: 4000, amount_centers: 13, amount_width: 1,
      },
      report: {
        chronological: { type: emptyMetrics, category: emptyMetrics, description: emptyMetrics },
        unseen_counterparty: null, training_samples: 60, validation_samples: 0, test_samples: 0,
        description_context: "independent", description_context_reason: "Synthetic fixture",
      },
    };
    query.state = { data: status };
    const html = renderPage();
    expect(html).toContain("synthetic-v1");
    expect(html).toContain("Alternatives only");
    expect(html).not.toContain("110%");
    expect(html).toContain("Minimum support: 6");
    expect(html).toContain("6 examples per label");
    expect(html).toContain("Category is useful context, not a confirmed fact");
    expect(html).toContain("Retrain model");
    expect(html).toContain("2 changed transactions");
    expect(html).toContain("Opening or refreshing this page never retrains");
    query.mutation = { isPending: true };
    expect(renderPage()).toContain("Training model");
    query.mutation = { isError: true, error: new Error("Training failed") };
    expect(renderPage()).toContain("Training failed");
    expect(html).toContain("More independent reviewed imports are needed");
    query.mutation = {};
    query.state = { data: { ...status, snapshot_id: null, algorithm: null, created_at: null, report: null } };
    const cold = renderPage();
    expect(cold).toContain("Not trained yet");
    expect(cold).toContain("Retrain model");
    expect(cold).not.toContain("Invalid Date");
  });
});
