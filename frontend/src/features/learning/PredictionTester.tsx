import { useMutation, useQuery } from "@tanstack/react-query";
import { FormEvent, useState } from "react";

import { api, LearningModelKind } from "../../lib/api";
import { useI18n } from "../../lib/i18n";

const copy = {
  en: { title: "Test a transaction", hint: "Use the signed bank amount: positive is incoming, negative is outgoing. Testing does not save or teach anything.", merchant: "Merchant or person", amount: "Signed amount", currency: "Currency", account: "Account", none: "Not specified", run: "Predict", waiting: "Calculating…", type: "Type", category: "Category", description: "Description", noSuggestion: "Review required", accepted: "Suggested", score: "Model score", limited: "Not calibrated", calibrated: "Validation calibrated", examples: "reviewed examples", details: "Inspect score contributions", explanation: "Contributions describe associations, not causes. Category contributions use the most likely type; its ranking considers all type probabilities. Description contributions describe the direct expert only, not the complete category blend.", descriptionHint: "Description combines direct transaction evidence with a capped, uncertainty-weighted category expert." },
  sv: { title: "Testa en transaktion", hint: "Använd bankens signerade belopp: positivt är inkommande, negativt är utgående. Testet sparar inget och lär inte modellen något.", merchant: "Handlare eller person", amount: "Signerat belopp", currency: "Valuta", account: "Konto", none: "Inte angivet", run: "Förutsäg", waiting: "Beräknar…", type: "Typ", category: "Kategori", description: "Beskrivning", noSuggestion: "Granskning krävs", accepted: "Föreslaget", score: "Modellpoäng", limited: "Inte kalibrerad", calibrated: "Kalibrerad på valideringsdata", examples: "granskade exempel", details: "Visa bidrag till poängen", explanation: "Bidragen beskriver samband, inte orsaker. Kategoribidragen använder den troligaste typen; rangordningen väger in alla typsannolikheter. Beskrivningsbidragen visar bara direktexperten, inte hela kategoriblandningen.", descriptionHint: "Beskrivningen kombinerar direkt transaktionsunderlag med en begränsad, osäkerhetsviktad kategoriexpert." },
};

export function PredictionTester() {
  const { locale } = useI18n();
  const c = copy[locale];
  const accounts = useQuery({ queryKey: ["accounts"], queryFn: api.listAccounts });
  const currencies = useQuery({ queryKey: ["currencies"], queryFn: api.listCurrencies });
  const categories = useQuery({ queryKey: ["categories"], queryFn: api.listCategories });
  const prediction = useMutation({ mutationFn: api.testPrediction });
  const [merchant, setMerchant] = useState("");
  const [amount, setAmount] = useState("50.00");
  const [currency, setCurrency] = useState("NOK");
  const [account, setAccount] = useState("");

  function submit(event: FormEvent) {
    event.preventDefault();
    prediction.mutate({ merchant: merchant.trim(), amount, currency_code: currency, account_id: account ? Number(account) : undefined });
  }

  return <section className="card space-y-5 p-5 sm:p-6">
    <div><h2>{c.title}</h2><p className="mt-2 text-sm text-muted">{c.hint}</p></div>
    <form onSubmit={submit} className="grid gap-4 sm:grid-cols-2">
      <label>{c.merchant}<input required maxLength={160} value={merchant} onChange={e => setMerchant(e.target.value)} /></label>
      <label>{c.amount}<input required type="number" step="0.01" value={amount} onChange={e => setAmount(e.target.value)} /></label>
      <label>{c.currency}<select value={currency} onChange={e => { setCurrency(e.target.value); setAccount(""); }}>{Array.from(new Set([currency, ...(currencies.data ?? []).map(item => item.code)])).map(code => <option key={code}>{code}</option>)}</select></label>
      <label>{c.account}<select value={account} onChange={e => setAccount(e.target.value)}><option value="">{c.none}</option>{accounts.data?.filter(item => item.currency_code === currency).map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
      <button className="primary-button sm:justify-self-start" disabled={prediction.isPending}>{prediction.isPending ? c.waiting : c.run}</button>
    </form>
    {prediction.isError && <p role="alert" className="alert error-alert">{prediction.error.message}</p>}
    {prediction.data && <div className="grid gap-4 lg:grid-cols-3" aria-live="polite">
      {(["type", "category", "description"] as LearningModelKind[]).map(kind => {
        const output = prediction.data.outputs[kind];
        return <article key={kind} className="min-w-0 rounded-xl border border-[#dce8df] p-4">
          <h3>{c[kind]}</h3><p className="my-2 text-sm font-semibold text-forest">{output.suggestion ? c.accepted : c.noSuggestion}</p>
          <p className="text-xs text-muted">{output.calibrated ? c.calibrated : c.limited}</p>
          {kind === "description" && <p className="mt-2 text-xs text-muted">{c.descriptionHint} {Math.round((output.context_weight ?? 0) * 100)}% {locale === "en" ? "category influence for this transaction." : "kategoripåverkan för denna transaktion."}</p>}
          <p className="mt-2 text-xs text-muted">{output.reason}</p>
          <ol className="mt-4 space-y-4">{output.candidates.map(candidate => {
            const category = kind === "category" ? categories.data?.find(item => String(item.id) === candidate.key) : undefined;
            const label = category ? category.localized_names[locale] ?? category.name : kind === "type" ? ({ en: { expense: "Expense", income: "Income", reimbursement: "Reimbursement", savings: "Savings", transfer: "Transfer" }, sv: { expense: "Utgift", income: "Inkomst", reimbursement: "Återbetalning", savings: "Sparande", transfer: "Överföring" } }[locale][candidate.key as "expense"]) ?? candidate.label : candidate.label;
            return <li key={candidate.key} className="break-words border-t border-[#e7eeea] pt-3">
              <strong>{label}</strong><p className="text-sm">{c.score}: {(candidate.probability * 100).toFixed(1)}%</p><p className="text-xs text-muted">{candidate.support} {c.examples}</p>
              {candidate.contributions.length > 0 && <details className="mt-2 text-xs"><summary className="cursor-pointer">{c.details}</summary><p className="my-2 text-muted">{c.explanation}</p><ul>{candidate.contributions.map(term => <li key={term.feature} className="flex justify-between gap-2 py-1"><span className="break-all">{term.feature}</span><span>{term.contribution > 0 ? "+" : ""}{term.contribution.toFixed(3)}</span></li>)}</ul></details>}
            </li>;
          })}</ol>
        </article>;
      })}
    </div>}
  </section>;
}
