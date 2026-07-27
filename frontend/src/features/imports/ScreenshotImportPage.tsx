import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChangeEvent, ClipboardEvent, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api, Transaction } from "../../lib/api";
import { useI18n } from "../../lib/i18n";
import { EditableImportRow, toApprovalRows, toEditableImportRow } from "./import-review";
import { getClipboardImage } from "./clipboard-image";

const transactionTypes: Transaction["transaction_type"][] = [
  "expense", "income", "reimbursement", "savings", "transfer",
];

const copy = {
  en: {
    eyebrow: "Screenshot import", title: "Import a transaction list", subtitle: "Your screenshot stays local. Nothing is saved as a transaction before review.",
    choose: "Choose screenshot", pasteHint: "You can also paste an image here with Ctrl+V.", account: "Account", imageReady: "Is this image clear and complete?", imageHint: "Check that dates, merchant text and every amount are visible before parsing.",
    replace: "Choose another", parse: "Confirm and parse", back: "Back to transactions", working: "Reading transaction rows", workingHint: "Recognizing text, separating rows and running both prediction models.",
    review: "Review extracted transactions", reviewHint: "Correct uncertain fields, add notes, reject unwanted rows, then approve.", accept: "Include", date: "Date", merchant: "Merchant", info: "Description", amount: "Signed source amount", type: "Type", category: "Category", notes: "Notes", optional: "Optional",
    source: "OCR source", extraction: "OCR", categoryConfidence: "Category", typeConfidence: "Type", descriptionConfidence: "Description", duplicate: "Possible duplicate", uncategorized: "Uncategorized", approve: "Approve selected transactions", approving: "Saving…", cancel: "Cancel", complete: "Import completed", completeHint: "Accepted rows were saved and all prediction models learned from your corrections.", noRows: "No rows were extracted.", selectAccount: "Select an account first.", imageTypes: "PNG, JPEG or WebP, maximum 15 MB.", rejected: "Exclude this row", storedSign: "Expenses, income and reimbursements are stored as positive magnitudes. Savings and transfers keep this sign.",
  },
  sv: {
    eyebrow: "Skärmbildsimport", title: "Importera en transaktionslista", subtitle: "Skärmbilden stannar lokalt. Inget sparas som transaktion före granskning.",
    choose: "Välj skärmbild", pasteHint: "Du kan även klistra in en bild här med Ctrl+V.", account: "Konto", imageReady: "Är bilden tydlig och komplett?", imageHint: "Kontrollera att datum, handlartext och alla belopp syns innan tolkning.",
    replace: "Välj en annan", parse: "Bekräfta och tolka", back: "Tillbaka till transaktioner", working: "Läser transaktionsrader", workingHint: "Känner igen text, delar upp rader och kör båda prediktionsmodellerna.",
    review: "Granska tolkade transaktioner", reviewHint: "Rätta osäkra fält, lägg till anteckningar, avvisa oönskade rader och godkänn sedan.", accept: "Inkludera", date: "Datum", merchant: "Handlare", info: "Beskrivning", amount: "Signerat källbelopp", type: "Typ", category: "Kategori", notes: "Anteckningar", optional: "Valfritt",
    source: "OCR-källa", extraction: "OCR", categoryConfidence: "Kategori", typeConfidence: "Typ", descriptionConfidence: "Beskrivning", duplicate: "Möjlig dubblett", uncategorized: "Okategoriserad", approve: "Godkänn valda transaktioner", approving: "Sparar…", cancel: "Avbryt", complete: "Importen är klar", completeHint: "Godkända rader sparades och alla prediktionsmodeller lärde sig av dina rättelser.", noRows: "Inga rader kunde tolkas.", selectAccount: "Välj ett konto först.", imageTypes: "PNG, JPEG eller WebP, högst 15 MB.", rejected: "Uteslut den här raden", storedSign: "Utgifter, inkomster och återbetalningar sparas som positiva belopp. Sparande och överföringar behåller tecknet.",
  },
} as const;

export function ScreenshotImportPage() {
  const { locale } = useI18n();
  const c = copy[locale];
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const accounts = useQuery({ queryKey: ["accounts"], queryFn: api.listAccounts });
  const categories = useQuery({ queryKey: ["categories"], queryFn: api.listCategories });
  const [file, setFile] = useState<File | null>(null);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [accountId, setAccountId] = useState(0);
  const [batchId, setBatchId] = useState<number | null>(null);
  const [rows, setRows] = useState<EditableImportRow[]>([]);
  const [finishedCount, setFinishedCount] = useState<number | null>(null);

  useEffect(() => { if (!accountId && accounts.data?.length) setAccountId(accounts.data[0].id); }, [accounts.data, accountId]);
  useEffect(() => () => { if (imageUrl?.startsWith("blob:")) URL.revokeObjectURL(imageUrl); }, [imageUrl]);

  const upload = useMutation({
    mutationFn: () => api.uploadScreenshot(file!, accountId),
    onSuccess: (batch) => setBatchId(batch.id),
  });
  const batch = useQuery({
    queryKey: ["screenshot-import", batchId],
    queryFn: () => api.getImportBatch(batchId!),
    enabled: batchId !== null,
    // OCR takes seconds, so sub-second full-batch polling creates needless API
    // and JSON work without making the progress display meaningfully smoother.
    refetchInterval: (query) =>
      ["queued", "processing"].includes(query.state.data?.status ?? "") ? 1500 : false,
  });
  useEffect(() => {
    if (batch.data?.status !== "review" || rows.length) return;
    setRows(batch.data.drafts.map(toEditableImportRow));
  }, [batch.data, rows.length]);

  const approve = useMutation({
    mutationFn: () => api.approveImport(batchId!, toApprovalRows(rows)),
    onSuccess: (result) => { setFinishedCount(result.created_transaction_ids.length); queryClient.invalidateQueries({ queryKey: ["transactions"] }); },
  });
  const categoryName = (id: number | null) => { const category = categories.data?.find((item) => item.id === id); return category?.localized_names?.[locale] ?? category?.localized_names?.en ?? category?.name ?? c.uncategorized; };
  const acceptedCount = rows.filter((row) => row.accepted).length;
  const currentImage = batchId ? api.importImageUrl(batchId) : imageUrl;

  function chooseFile(event: ChangeEvent<HTMLInputElement>) {
    selectFile(event.target.files?.[0] ?? null);
  }
  function selectFile(next: File | null) {
    if (imageUrl?.startsWith("blob:")) URL.revokeObjectURL(imageUrl);
    setFile(next); setBatchId(null); setRows([]); setFinishedCount(null);
    setImageUrl(next ? URL.createObjectURL(next) : null);
  }
  function pasteImage(event: ClipboardEvent<HTMLElement>) {
    const pasted = getClipboardImage(event.clipboardData.items);
    if (!pasted) return;
    event.preventDefault();
    const extension = pasted.type.split("/")[1] || "png";
    selectFile(new File([pasted], `pasted-screenshot.${extension}`, { type: pasted.type }));
  }
  function updateRow(id: number, changes: Partial<EditableImportRow>) { setRows((current) => current.map((row) => row.draft_id === id ? { ...row, ...changes } : row)); }

  return <div className="space-y-6"><header className="flex flex-wrap items-end justify-between gap-4"><div><p className="eyebrow">{c.eyebrow}</p><h1>{c.title}</h1><p className="page-subtitle">{c.subtitle}</p></div><Link className="secondary-button no-underline" to="/transactions">← {c.back}</Link></header>
    {!batchId && <section className="card grid gap-6 p-6 lg:grid-cols-[360px_1fr]" onPaste={pasteImage} tabIndex={0} aria-label={c.choose}>
      <div className="space-y-4"><label>{c.account}<select value={accountId} onChange={(event) => setAccountId(Number(event.target.value))}>{accounts.data?.map((account) => <option key={account.id} value={account.id}>{account.name} · {account.currency_code}</option>)}</select></label><label className="flex cursor-pointer items-center justify-center rounded-xl border-2 border-dashed border-[#b9d0c0] bg-[#f5faf6] p-8 text-center text-sm font-bold text-forest hover:bg-[#edf6ef]"><input className="sr-only" type="file" accept="image/png,image/jpeg,image/webp" onChange={chooseFile} />{file ? c.replace : `＋ ${c.choose}`}</label><p className="text-xs text-muted">{c.imageTypes} {c.pasteHint}</p></div>
      <div className="min-h-72 overflow-hidden rounded-2xl border border-[#dce8df] bg-[#eef3ef]">{imageUrl ? <img className="h-full max-h-[520px] w-full object-contain" src={imageUrl} alt={file?.name ?? c.choose} /> : <div className="grid h-full min-h-72 place-items-center text-sm text-muted">{c.choose}</div>}</div>
      {file && <div className="lg:col-span-2 flex flex-wrap items-center justify-between gap-4 rounded-xl bg-[#f5f9f5] p-5"><div><strong className="block text-forest">{c.imageReady}</strong><p className="mb-0 text-sm text-muted">{c.imageHint}</p></div><button className="primary-button" disabled={!accountId || upload.isPending} onClick={() => upload.mutate()}>{upload.isPending ? c.working : c.parse}</button></div>}
      {upload.isError && <div className="alert error-alert lg:col-span-2">{(upload.error as Error).message}</div>}
    </section>}

    {batchId && batch.data && ["queued", "processing"].includes(batch.data.status) && <section className="card mx-auto max-w-2xl p-8 text-center"><div className="mx-auto mb-5 grid h-16 w-16 animate-pulse place-items-center rounded-2xl bg-[#e4f0e7] text-2xl">⌁</div><h2>{c.working}</h2><p className="page-subtitle mb-6">{c.workingHint}</p><div className="h-3 overflow-hidden rounded-full bg-[#e4ece6]"><div className="h-full rounded-full bg-forest-light transition-all" style={{ width: `${batch.data.progress}%` }} /></div><strong className="mt-3 block text-sm text-forest">{batch.data.progress}%</strong></section>}
    {batch.data?.status === "error" && <section className="alert error-alert"><strong>{batch.data.error_message}</strong><button className="secondary-button ml-4" onClick={() => { setBatchId(null); setRows([]); }}>{c.replace}</button></section>}
    {finishedCount !== null && <section className="card mx-auto max-w-xl p-8 text-center"><div className="mx-auto mb-4 grid h-16 w-16 place-items-center rounded-full bg-[#dff0e4] text-2xl text-forest">✓</div><h2>{c.complete}</h2><p className="page-subtitle">{finishedCount} · {c.completeHint}</p><button className="primary-button mt-6" onClick={() => navigate("/transactions")}>{c.back}</button></section>}

    {batch.data?.status === "review" && finishedCount === null && <div className="fixed inset-0 z-50 overflow-y-auto bg-[#10251f]/65 p-3 backdrop-blur-sm sm:p-8" role="dialog" aria-modal="true" aria-labelledby="import-review-title"><div className="card mx-auto max-w-6xl overflow-hidden">
      <div className="sticky top-0 z-10 flex flex-wrap items-center justify-between gap-4 border-b border-[#dfe9e1] bg-white/95 p-5 backdrop-blur"><div><p className="eyebrow">{c.eyebrow}</p><h2 id="import-review-title">{c.review}</h2><p className="page-subtitle">{c.reviewHint}</p></div><div className="flex gap-2"><button className="secondary-button" onClick={() => navigate("/transactions")}>{c.cancel}</button><button className="primary-button" disabled={!acceptedCount || approve.isPending} onClick={() => approve.mutate()}>{approve.isPending ? c.approving : `${c.approve} (${acceptedCount})`}</button></div></div>
      <div className="grid gap-5 p-5 xl:grid-cols-[300px_1fr]"><aside className="xl:sticky xl:top-32 xl:self-start"><img className="max-h-[72vh] w-full rounded-xl border border-[#dce8df] object-contain" src={currentImage ?? ""} alt={batch.data.original_filename} /><p className="mt-3 text-xs text-muted">{c.storedSign}</p></aside><div className="space-y-4">{rows.length ? rows.map((row, index) => <ReviewRow key={row.draft_id} row={row} index={index} copy={c} accounts={accounts.data ?? []} categories={categories.data ?? []} categoryName={categoryName} update={updateRow} />) : <p>{c.noRows}</p>}</div></div>
      {approve.isError && <div className="alert error-alert m-5">{(approve.error as Error).message}</div>}
    </div></div>}
  </div>;
}

function ReviewRow({ row, index, copy: c, accounts, categories, categoryName, update }: { row: EditableImportRow; index: number; copy: typeof copy.en | typeof copy.sv; accounts: Awaited<ReturnType<typeof api.listAccounts>>; categories: Awaited<ReturnType<typeof api.listCategories>>; categoryName: (id: number | null) => string; update: (id: number, changes: Partial<EditableImportRow>) => void }) {
  const tone = (value: number) => value >= .8 ? "bg-[#e2f2e7] text-[#2e6b4d]" : value >= .55 ? "bg-[#fff2d8] text-[#8a6425]" : "bg-[#f9e4e1] text-[#96574e]";
  return <article className={`rounded-2xl border p-5 transition ${row.accepted ? "border-[#dce8df] bg-white" : "border-[#e2e5e3] bg-[#f4f5f4] opacity-65"}`}><div className="mb-4 flex flex-wrap items-center gap-2"><strong className="mr-auto text-forest">#{index + 1} · {row.merchant || c.merchant}</strong>{[[c.extraction, row.extraction_confidence], [c.categoryConfidence, row.category_confidence], [c.typeConfidence, row.type_confidence], [c.descriptionConfidence, row.description_confidence]].map(([label, value]) => <span key={String(label)} className={`rounded-full px-2 py-1 text-[.68rem] font-bold ${tone(Number(value))}`}>{label} {Math.round(Number(value) * 100)}%</span>)}{row.possible_duplicate && <span className="rounded-full bg-[#fde4df] px-2 py-1 text-[.68rem] font-bold text-[#9b5148]">⚠ {c.duplicate}</span>}</div>
    <label className="mb-4 flex flex-row items-center gap-2"><input className="min-h-0 w-4" type="checkbox" checked={row.accepted} onChange={(event) => update(row.draft_id, { accepted: event.target.checked })} />{row.accepted ? c.accept : c.rejected}</label>
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3"><label>{c.date}<input type="date" value={row.transaction_date} onChange={(event) => update(row.draft_id, { transaction_date: event.target.value })} required /></label><label>{c.merchant}<input value={row.merchant} onChange={(event) => update(row.draft_id, { merchant: event.target.value })} required /></label><label>{c.amount}<input type="number" step="0.01" value={row.signed_amount} onChange={(event) => update(row.draft_id, { signed_amount: event.target.value })} required /></label><label>{c.type}<select value={row.transaction_type} onChange={(event) => update(row.draft_id, { transaction_type: event.target.value as Transaction["transaction_type"] })}>{transactionTypes.map((type) => <option key={type}>{type}</option>)}</select></label><label>{c.category}<select value={row.category_id ?? ""} onChange={(event) => update(row.draft_id, { category_id: event.target.value ? Number(event.target.value) : null })}><option value="">{c.uncategorized}</option>{categories.map((category) => <option key={category.id} value={category.id}>{categoryName(category.id)}</option>)}</select></label><label>{c.account}<select value={row.account_id} onChange={(event) => update(row.draft_id, { account_id: Number(event.target.value), currency_code: accounts.find((account) => account.id === Number(event.target.value))?.currency_code ?? row.currency_code })}>{accounts.map((account) => <option key={account.id} value={account.id}>{account.name} · {account.currency_code}</option>)}</select></label><label className="lg:col-span-3">{c.info} <span className="font-normal text-muted">({c.optional})</span><input value={row.description ?? ""} onChange={(event) => update(row.draft_id, { description: event.target.value })} /></label><label className="lg:col-span-3">{c.notes} <span className="font-normal text-muted">({c.optional})</span><textarea rows={2} value={row.notes ?? ""} onChange={(event) => update(row.draft_id, { notes: event.target.value })} /></label></div>
    {!!row.validation_errors.length && <div className="mt-3 rounded-lg bg-[#fff0ed] p-3 text-xs text-[#93574e]">{row.validation_errors.join(" · ")}</div>}<details className="mt-3 text-xs text-muted"><summary className="cursor-pointer font-bold text-[#587267]">{c.source}</summary><p className="mt-2 rounded-lg bg-[#f3f6f3] p-3 font-mono leading-5">{row.raw_text}</p></details>
  </article>;
}
