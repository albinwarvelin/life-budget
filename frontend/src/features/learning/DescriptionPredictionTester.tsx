import { useMutation } from "@tanstack/react-query";
import { FormEvent, useState } from "react";

import { api, Category, Transaction } from "../../lib/api";
import { Locale } from "../../lib/i18n";

const transactionTypes: Transaction["transaction_type"][] = [
  "expense", "income", "reimbursement", "savings", "transfer",
];

const copy = {
  en: {
    eyebrow: "Prediction laboratory", title: "Test a description prediction",
    hint: "This calls the real API without teaching the model or saving a transaction.",
    merchant: "Merchant", amount: "Amount", currency: "Currency", category: "Category",
    type: "Transaction type", none: "Not provided", run: "Calculate prediction",
    noSuggestion: "No suggestion passed the confidence threshold", confidence: "confidence",
    candidates: "Candidate calculations", signal: "Signal", matched: "Matched memory",
    conditional: "Within signal", baseline: "Overall baseline", reliability: "Reliability",
    similarity: "Similarity", contribution: "Score contribution", observations: "Matches",
    relative: "Relative evidence", score: "Score", showMore: "Show more signals", showLess: "Show fewer signals",
  },
  sv: {
    eyebrow: "Prediktionslaboratorium", title: "Testa en beskrivningsprediktion",
    hint: "Detta anropar det riktiga API:t utan att lära modellen eller spara en transaktion.",
    merchant: "Handlare", amount: "Belopp", currency: "Valuta", category: "Kategori",
    type: "Transaktionstyp", none: "Ej angivet", run: "Beräkna prediktion",
    noSuggestion: "Inget förslag klarade konfidensgränsen", confidence: "konfidens",
    candidates: "Kandidatberäkningar", signal: "Signal", matched: "Matchat minne",
    conditional: "Inom signalen", baseline: "Övergripande basnivå", reliability: "Tillförlitlighet",
    similarity: "Likhet", contribution: "Poängbidrag", observations: "Matchningar",
    relative: "Relativt bevis", score: "Poäng", showMore: "Visa fler signaler", showLess: "Visa färre signaler",
  },
} as const;

export function DescriptionPredictionTester({
  categories,
  locale,
}: {
  categories: Category[];
  locale: Locale;
}) {
  const c = copy[locale];
  const [merchant, setMerchant] = useState("");
  const [amount, setAmount] = useState("0.00");
  const [currency, setCurrency] = useState("SEK");
  const [categoryId, setCategoryId] = useState("");
  const [transactionType, setTransactionType] = useState<Transaction["transaction_type"] | "">("expense");
  const [expandedCandidates, setExpandedCandidates] = useState<Record<string, boolean>>({});
  const prediction = useMutation({ mutationFn: api.testDescriptionPrediction });

  function submit(event: FormEvent) {
    event.preventDefault();
    prediction.mutate({
      merchant,
      amount,
      currency_code: currency,
      category_id: categoryId ? Number(categoryId) : undefined,
      transaction_type: transactionType || undefined,
    });
  }

  return <section className="card overflow-hidden">
    <div className="border-b border-[#e2ebe4] bg-[#f6fbf6] p-6">
      <p className="eyebrow">{c.eyebrow}</p><h2>{c.title}</h2><p className="page-subtitle">{c.hint}</p>
      <form className="mt-5 grid items-end gap-3 md:grid-cols-2 xl:grid-cols-6" onSubmit={submit}>
        <label className="xl:col-span-2">{c.merchant}<input required value={merchant} onChange={(event) => setMerchant(event.target.value)} /></label>
        <label>{c.amount}<input required inputMode="decimal" value={amount} onChange={(event) => setAmount(event.target.value)} /></label>
        <label>{c.currency}<select value={currency} onChange={(event) => setCurrency(event.target.value)}><option>SEK</option><option>NOK</option></select></label>
        <label>{c.category}<select value={categoryId} onChange={(event) => setCategoryId(event.target.value)}><option value="">{c.none}</option>{categories.map((category) => <option key={category.id} value={category.id}>{category.localized_names[locale] ?? category.name}</option>)}</select></label>
        <label>{c.type}<select value={transactionType} onChange={(event) => setTransactionType(event.target.value as Transaction["transaction_type"] | "")}><option value="">{c.none}</option>{transactionTypes.map((type) => <option key={type}>{type}</option>)}</select></label>
        <button className="primary-button md:col-span-2 xl:col-span-6 xl:justify-self-start" disabled={prediction.isPending}>{c.run}</button>
      </form>
      {prediction.isError && <div className="alert error-alert mt-4">{(prediction.error as Error).message}</div>}
    </div>

    {prediction.data && <div className="space-y-6 p-6">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div><p className="text-xs font-bold uppercase tracking-[.12em] text-[#668277]">{prediction.data.description ?? c.noSuggestion}</p><p className="mt-1 text-sm text-muted">{prediction.data.reason}</p></div>
        <strong className="text-2xl text-forest">{(prediction.data.confidence * 100).toFixed(1)}% <small className="text-xs font-normal text-muted">{c.confidence}</small></strong>
      </div>
      <div><h3>{c.candidates}</h3><div className="mt-4 space-y-5">{prediction.data.candidates.map((candidate) => {
        const expanded = expandedCandidates[candidate.description] ?? false;
        const visibleContributions = expanded ? candidate.contributions : candidate.contributions.slice(0, 3);
        return <section key={candidate.description} className="rounded-xl border border-[#dfe9e1] p-4">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2"><strong>{candidate.description}</strong><span className="text-xs text-muted">{c.score} {candidate.score.toFixed(3)} · {c.relative} {(candidate.relative_score * 100).toFixed(1)}%</span></div>
          <div className="overflow-x-auto"><table><thead><tr><th>{c.signal}</th><th>{c.matched}</th><th>{c.conditional}</th><th>{c.baseline}</th><th>{c.reliability}</th><th>{c.similarity}</th><th>{c.observations}</th><th className="amount-cell">{c.contribution}</th></tr></thead><tbody>{visibleContributions.map((item) => <tr key={`${item.signal_type}:${item.signal_value}`}><td><code>{item.signal_type}</code><small className="cell-note">{readableSignal(item.signal_type, item.signal_value, categories, locale)}</small></td><td>{readableSignal(item.signal_type, item.matched_value, categories, locale)}</td><td>{(item.conditional_probability * 100).toFixed(1)}%</td><td>{(item.baseline_probability * 100).toFixed(1)}%</td><td>{(item.reliability * 100).toFixed(1)}%</td><td>{(item.similarity * 100).toFixed(1)}%</td><td>{item.observations}</td><td className="amount-cell">+{item.contribution.toFixed(3)}</td></tr>)}</tbody></table></div>
          {candidate.contributions.length > 3 && <button type="button" className="text-button mt-3" onClick={() => setExpandedCandidates((current) => ({ ...current, [candidate.description]: !expanded }))}>{expanded ? c.showLess : `${c.showMore} (${candidate.contributions.length - 3})`}</button>}
        </section>;
      })}</div></div>
    </div>}
  </section>;
}

function readableSignal(
  signalType: string,
  value: string,
  categories: Category[],
  locale: Locale,
) {
  const parts = value.split("|");
  const categoryIndex = signalType === "category" || signalType.startsWith("category_")
    ? 0
    : signalType.includes("category")
      ? 1
      : -1;
  if (categoryIndex < 0 || !parts[categoryIndex]) return value;
  const category = categories.find((item) => String(item.id) === parts[categoryIndex]);
  if (!category) return value;
  const label = category.localized_names[locale] ?? category.name;
  if (signalType === "category") return label;
  parts[categoryIndex] = label;
  return parts.join(" / ");
}
