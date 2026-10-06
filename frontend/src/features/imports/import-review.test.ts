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
  it("requires a reviewed type when the model abstains", () => {
    const row = toEditableImportRow({ ...draft, predicted_transaction_type: null });
    expect(row.transaction_type).toBe("");
    expect(() => toApprovalRows([row])).toThrow("Choose a transaction type");
    expect(toApprovalRows([{ ...row, accepted: false }])[0].accepted).toBe(false);
  });
  it("keeps incomplete OCR fields editable with their validation errors", () => {
    const row = toEditableImportRow({ ...draft, transaction_date: null, signed_amount: null,
      validation_errors: ["Date could not be read", "Amount could not be read"] });
    expect(row.transaction_date).toBe("");
    expect(row.signed_amount).toBe("");
    expect(row.validation_errors).toEqual(["Date could not be read", "Amount could not be read"]);
    const [approved] = toApprovalRows([{ ...row, transaction_date: "2026-09-05", signed_amount: "-123.45" }]);
    expect(approved.transaction_date).toBe("2026-09-05");
    expect(approved.signed_amount).toBe("-123.45");
  });

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
