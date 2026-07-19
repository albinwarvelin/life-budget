import { describe, expect, it } from "vitest";

import { ImportDraft } from "../../lib/api";
import { toApprovalRows, toEditableImportRow } from "./import-review";

const draft: ImportDraft = {
  id: 7, row_index: 0, raw_text: "2026-07-18 ICA -245,50 SEK", raw_amount_text: "-245,50",
  source_bounds: null, transaction_date: "2026-07-18", merchant: "ICA", description: "Kortköp", predicted_description: "Kortköp",
  signed_amount: "-245.50", currency_code: "SEK", account_id: 2, predicted_category_id: 3,
  predicted_transaction_type: "expense", category_confidence: .8, type_confidence: .7, description_confidence: .6,
  extraction_confidence: .9, validation_errors: [], possible_duplicate: false, status: "pending",
};

describe("screenshot import review mapping", () => {
  it("starts with parser predictions but keeps the signed source amount", () => {
    const row = toEditableImportRow(draft);
    expect(row).toMatchObject({ draft_id: 7, accepted: true, signed_amount: "-245.50", transaction_type: "expense", category_id: 3 });
  });

  it("submits corrections without sending private OCR evidence back unnecessarily", () => {
    const row = { ...toEditableImportRow(draft), merchant: "ICA Nära", notes: "Weekly shop" };
    const [approved] = toApprovalRows([row]);
    expect(approved.merchant).toBe("ICA Nära");
    expect(approved.notes).toBe("Weekly shop");
    expect(approved).not.toHaveProperty("raw_text");
    expect(approved).not.toHaveProperty("extraction_confidence");
  });
});
