import { ApprovedImportRow, ImportDraft } from "../../lib/api";

export type EditableImportRow = ApprovedImportRow & Pick<ImportDraft,
  "raw_text" | "raw_amount_text" | "extraction_confidence" | "category_confidence" |
  "type_confidence" | "possible_duplicate" | "validation_errors"
  | "description_confidence"
>;

/** Convert immutable parser output into the user's editable review state. */
export function toEditableImportRow(draft: ImportDraft): EditableImportRow {
  return {
    draft_id: draft.id,
    accepted: true,
    transaction_date: draft.transaction_date ?? "",
    merchant: draft.merchant ?? "",
    description: draft.description ?? "",
    signed_amount: draft.signed_amount ?? "",
    currency_code: draft.currency_code,
    account_id: draft.account_id,
    transaction_type: draft.predicted_transaction_type ?? "expense",
    category_id: draft.predicted_category_id,
    notes: "",
    raw_text: draft.raw_text,
    raw_amount_text: draft.raw_amount_text,
    extraction_confidence: draft.extraction_confidence,
    category_confidence: draft.category_confidence,
    type_confidence: draft.type_confidence,
    description_confidence: draft.description_confidence,
    possible_duplicate: draft.possible_duplicate,
    validation_errors: draft.validation_errors,
  };
}

/** Strip OCR-only evidence before submitting final, user-confirmed values. */
export function toApprovalRows(rows: EditableImportRow[]): ApprovedImportRow[] {
  return rows.map(({ raw_text: _raw, raw_amount_text: _amount, extraction_confidence: _ocr,
    category_confidence: _category, type_confidence: _type,
    description_confidence: _description, possible_duplicate: _duplicate,
    validation_errors: _errors, ...approved }) => approved);
}
