import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { api, LearningPattern, Transaction } from "../../lib/api";
import { calculateEvidenceProbabilities } from "../../lib/learning-model";
import { useI18n } from "../../lib/i18n";

const palette = ["#2e6b5a", "#a86d32", "#5573a5", "#9a5274", "#6c7d32", "#7357a6"];
const transactionTypes: Transaction["transaction_type"][] = [
  "expense", "income", "reimbursement", "savings", "transfer",
];

const copy = {
  en: {
    eyebrow: "Category intelligence", title: "Learning model explorer",
    subtitle: "Follow the evidence from remembered phrases to category suggestions.", back: "Back to settings",
    events: "Learning events", connections: "Connections", phrases: "Stored phrases", categories: "Categories",
    map: "Interactive connection map", mapHint: "Select a phrase or connection to focus the graph.",
    search: "Find a phrase", allSignals: "All signal types", allAccounts: "All account scopes", global: "Global only",
    allTypes: "All transaction types", observations: "Minimum observations", noConnections: "No connections match these filters.",
    evidence: "Evidence distribution", evidenceHint: "Relative stored weight for this exact phrase across categories.",
    choosePhrase: "Choose a phrase in the map to inspect its category probabilities.", weight: "weight", seen: "observations",
    notCalibrated: "These percentages compare this model's stored evidence. They are explanatory scores, not calibrated real-world probabilities.",
    lab: "Live prediction lab", labHint: "Try a draft transaction. The real prediction service runs after you stop typing for one second.",
    merchant: "Merchant", description: "Description", account: "Account", type: "Transaction type", optional: "Optional",
    waiting: "Enter a merchant to test the model.", thinking: "Following learned connections…", noSuggestion: "No learned suggestion yet.",
    scoring: "How scoring works", exact: "Signal weight", accountBoost: "Same-account multiplier", fuzzy: "Fuzzy match threshold",
  },
  sv: {
    eyebrow: "Kategoriintelligens", title: "Utforska inlärningsmodellen",
    subtitle: "Följ bevisen från sparade fraser till kategoriförslag.", back: "Tillbaka till inställningar",
    events: "Inlärningshändelser", connections: "Kopplingar", phrases: "Sparade fraser", categories: "Kategorier",
    map: "Interaktiv kopplingskarta", mapHint: "Välj en fras eller koppling för att fokusera grafen.",
    search: "Sök efter en fras", allSignals: "Alla signaltyper", allAccounts: "Alla kontoomfång", global: "Endast globalt",
    allTypes: "Alla transaktionstyper", observations: "Minsta antal observationer", noConnections: "Inga kopplingar matchar filtren.",
    evidence: "Bevisfördelning", evidenceHint: "Relativ sparad vikt för exakt den här frasen mellan kategorier.",
    choosePhrase: "Välj en fras i kartan för att se dess kategorisannolikheter.", weight: "vikt", seen: "observationer",
    notCalibrated: "Procentsatserna jämför modellens sparade bevis. De är förklarande poäng, inte kalibrerade verkliga sannolikheter.",
    lab: "Live-labb för förutsägelser", labHint: "Prova ett transaktionsutkast. Tjänsten körs en sekund efter att du slutat skriva.",
    merchant: "Handlare", description: "Beskrivning", account: "Konto", type: "Transaktionstyp", optional: "Valfritt",
    waiting: "Ange en handlare för att testa modellen.", thinking: "Följer inlärda kopplingar…", noSuggestion: "Inget inlärt förslag ännu.",
    scoring: "Så fungerar poängen", exact: "Signalvikt", accountBoost: "Multiplikator för samma konto", fuzzy: "Tröskel för ungefärlig matchning",
  },
} as const;

type PhraseNode = { key: string; type: string; text: string; weight: number };

export function LearningModelPage() {
  const { locale } = useI18n();
  const c = copy[locale];
  const model = useQuery({ queryKey: ["learning-model"], queryFn: api.getLearningModel });
  const accounts = useQuery({ queryKey: ["accounts"], queryFn: api.listAccounts });
  const [search, setSearch] = useState("");
  const [signal, setSignal] = useState("all");
  const [accountScope, setAccountScope] = useState("all");
  const [transactionType, setTransactionType] = useState("all");
  const [minimumObservations, setMinimumObservations] = useState(1);
  const [selectedPhrase, setSelectedPhrase] = useState<string | null>(null);

  const categoryMap = useMemo(() => new Map(model.data?.categories.map((category) => [category.id, category]) ?? []), [model.data]);
  const categoryName = (id: number) => {
    const category = categoryMap.get(id);
    return category?.localized_names?.[locale] ?? category?.localized_names?.en ?? category?.name ?? `#${id}`;
  };

  const filteredPatterns = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase();
    return (model.data?.patterns ?? []).filter((pattern) =>
      (!needle || pattern.pattern_text.toLocaleLowerCase().includes(needle)) &&
      (signal === "all" || pattern.pattern_type === signal) &&
      (accountScope === "all" || (accountScope === "global" ? pattern.account_id === null : pattern.account_id === Number(accountScope))) &&
      (transactionType === "all" || pattern.transaction_type === transactionType) &&
      pattern.observations >= minimumObservations,
    );
  }, [model.data, search, signal, accountScope, transactionType, minimumObservations]);

  const graph = useMemo(() => {
    const phraseTotals = new Map<string, PhraseNode>();
    for (const pattern of filteredPatterns) {
      const key = `${pattern.pattern_type}:${pattern.pattern_text}`;
      const node = phraseTotals.get(key) ?? { key, type: pattern.pattern_type, text: pattern.pattern_text, weight: 0 };
      node.weight += pattern.weight;
      phraseTotals.set(key, node);
    }
    const phrases = [...phraseTotals.values()].sort((a, b) => b.weight - a.weight).slice(0, 24);
    const phraseKeys = new Set(phrases.map((phrase) => phrase.key));
    const edges = filteredPatterns.filter((pattern) => phraseKeys.has(`${pattern.pattern_type}:${pattern.pattern_text}`)).slice(0, 90);
    const categoryIds = [...new Set(edges.map((pattern) => pattern.category_id))];
    return { phrases, edges, categoryIds };
  }, [filteredPatterns]);

  useEffect(() => {
    if (selectedPhrase && !graph.phrases.some((phrase) => phrase.key === selectedPhrase)) setSelectedPhrase(null);
  }, [graph.phrases, selectedPhrase]);

  const selectedNode = graph.phrases.find((phrase) => phrase.key === selectedPhrase);
  const evidence = selectedNode
    ? calculateEvidenceProbabilities(filteredPatterns, selectedNode.type, selectedNode.text)
    : [];
  const signalTypes = [...new Set(model.data?.patterns.map((pattern) => pattern.pattern_type) ?? [])].sort();
  const uniquePhraseCount = new Set(model.data?.patterns.map((pattern) => `${pattern.pattern_type}:${pattern.pattern_text}`)).size;
  const graphHeight = Math.max(520, Math.max(graph.phrases.length, graph.categoryIds.length) * 43 + 90);
  const phraseY = (index: number) => 65 + index * ((graphHeight - 120) / Math.max(graph.phrases.length - 1, 1));
  const categoryY = (index: number) => 65 + index * ((graphHeight - 120) / Math.max(graph.categoryIds.length - 1, 1));

  if (model.isLoading) return <div className="grid min-h-[55vh] place-items-center text-muted">Loading model…</div>;
  if (model.isError) return <div className="alert error-alert">{(model.error as Error).message}</div>;

  return <div className="space-y-7">
    <header className="flex flex-wrap items-end justify-between gap-5">
      <div><p className="eyebrow">{c.eyebrow}</p><h1>{c.title}</h1><p className="page-subtitle max-w-2xl">{c.subtitle}</p></div>
      <Link className="secondary-button no-underline" to="/settings">← {c.back}</Link>
    </header>

    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {[[c.events, model.data!.event_count], [c.connections, model.data!.patterns.length], [c.phrases, uniquePhraseCount], [c.categories, model.data!.categories.length]].map(([label, value]) =>
        <div className="card overflow-hidden p-5" key={label}><p className="text-xs font-bold uppercase tracking-[.12em] text-[#668277]">{label}</p><strong className="mt-2 block text-3xl text-forest">{value}</strong></div>)}
    </div>

    <section className="card overflow-hidden">
      <div className="border-b border-[#e2ebe4] bg-gradient-to-r from-[#f6fbf6] to-white p-6">
        <p className="eyebrow">{c.map}</p><h2>{c.map}</h2><p className="page-subtitle">{c.mapHint}</p>
        <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-5">
          <label>{c.search}<input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="ICA, coffee…" /></label>
          <label>{c.exact}<select value={signal} onChange={(event) => setSignal(event.target.value)}><option value="all">{c.allSignals}</option>{signalTypes.map((item) => <option key={item}>{item}</option>)}</select></label>
          <label>{c.account}<select value={accountScope} onChange={(event) => setAccountScope(event.target.value)}><option value="all">{c.allAccounts}</option><option value="global">{c.global}</option>{accounts.data?.map((account) => <option value={account.id} key={account.id}>{account.name}</option>)}</select></label>
          <label>{c.type}<select value={transactionType} onChange={(event) => setTransactionType(event.target.value)}><option value="all">{c.allTypes}</option>{transactionTypes.map((item) => <option key={item}>{item}</option>)}</select></label>
          <label>{c.observations}<input type="number" min="1" value={minimumObservations} onChange={(event) => setMinimumObservations(Math.max(1, Number(event.target.value)))} /></label>
        </div>
      </div>

      {!graph.edges.length ? <div className="p-12 text-center text-muted">{c.noConnections}</div> :
        <div className="grid xl:grid-cols-[minmax(0,1fr)_340px]">
          <div className="min-w-0 overflow-auto bg-[radial-gradient(circle_at_center,#edf4ef_1px,transparent_1px)] [background-size:22px_22px]">
            <svg className="min-w-[860px] w-full" viewBox={`0 0 1000 ${graphHeight}`} role="img" aria-label={c.map}>
              <text x="70" y="28" className="fill-[#668277] text-[11px] font-bold uppercase tracking-widest">{c.phrases}</text>
              <text x="790" y="28" className="fill-[#668277] text-[11px] font-bold uppercase tracking-widest">{c.categories}</text>
              {graph.edges.map((edge) => {
                const key = `${edge.pattern_type}:${edge.pattern_text}`;
                const left = graph.phrases.findIndex((phrase) => phrase.key === key);
                const right = graph.categoryIds.indexOf(edge.category_id);
                const focused = !selectedPhrase || selectedPhrase === key;
                const color = palette[right % palette.length];
                return <path key={edge.id} d={`M 285 ${phraseY(left)} C 470 ${phraseY(left)}, 530 ${categoryY(right)}, 715 ${categoryY(right)}`} fill="none" stroke={color} strokeWidth={Math.min(8, 1 + Math.sqrt(edge.weight))} opacity={focused ? .62 : .07} className="cursor-pointer transition-opacity" onClick={() => setSelectedPhrase(key)}><title>{`${edge.pattern_text} → ${categoryName(edge.category_id)} · ${Math.round(edge.weight * 100) / 100}`}</title></path>;
              })}
              {graph.phrases.map((phrase, index) => {
                const selected = phrase.key === selectedPhrase;
                return <g key={phrase.key} role="button" tabIndex={0} aria-label={phrase.text} className="cursor-pointer outline-none" onClick={() => setSelectedPhrase(selected ? null : phrase.key)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") setSelectedPhrase(selected ? null : phrase.key); }}>
                  <rect x="55" y={phraseY(index) - 18} width="230" height="36" rx="11" fill={selected ? "#173a32" : "white"} stroke={selected ? "#173a32" : "#cadbd0"} strokeWidth={selected ? 2 : 1} />
                  <text x="70" y={phraseY(index) + 4} fill={selected ? "white" : "#203a31"} className="text-[12px] font-semibold">{phrase.text.length > 26 ? `${phrase.text.slice(0, 25)}…` : phrase.text}</text>
                  <title>{`${phrase.type}: ${phrase.text}`}</title>
                </g>;
              })}
              {graph.categoryIds.map((categoryId, index) => <g key={categoryId}>
                <circle cx="735" cy={categoryY(index)} r="7" fill={palette[index % palette.length]} />
                <rect x="753" y={categoryY(index) - 18} width="205" height="36" rx="11" fill="white" stroke="#cadbd0" />
                <text x="769" y={categoryY(index) + 4} className="fill-[#203a31] text-[12px] font-bold">{categoryName(categoryId)}</text>
              </g>)}
            </svg>
          </div>
          <aside className="border-t border-[#e2ebe4] bg-[#fbfdfb] p-6 xl:border-t-0 xl:border-l">
            <p className="eyebrow">{c.evidence}</p><h2 className="break-words">{selectedNode?.text ?? c.evidence}</h2><p className="page-subtitle mb-5">{selectedNode ? `${selectedNode.type} · ${c.evidenceHint}` : c.choosePhrase}</p>
            <div className="space-y-5">{evidence.map((item, index) => <div key={item.categoryId}>
              <div className="mb-1 flex items-center justify-between gap-3 text-sm"><strong>{categoryName(item.categoryId)}</strong><span className="font-bold" style={{ color: palette[index % palette.length] }}>{(item.probability * 100).toFixed(1)}%</span></div>
              <div className="h-2 overflow-hidden rounded-full bg-[#e4ece6]"><div className="h-full rounded-full transition-all duration-500" style={{ width: `${item.probability * 100}%`, backgroundColor: palette[index % palette.length] }} /></div>
              <p className="mt-1 text-xs text-muted">{item.weight.toFixed(2)} {c.weight} · {item.observations} {c.seen}</p>
            </div>)}</div>
            {selectedNode && <p className="mt-7 rounded-xl bg-[#edf5ef] p-4 text-xs leading-5 text-[#4f695f]">{c.notCalibrated}</p>}
          </aside>
        </div>}
    </section>

    <div className="grid gap-6 xl:grid-cols-[1.4fr_1fr]"><PredictionLab accounts={accounts.data ?? []} categories={categoryMap} locale={locale} text={c} /><ScoringCard model={model.data!} text={c} /></div>
  </div>;
}

function PredictionLab({ accounts, categories, locale, text }: { accounts: Awaited<ReturnType<typeof api.listAccounts>>; categories: Map<number, { id: number; name: string; localized_names: Record<string, string> }>; locale: "en" | "sv"; text: typeof copy.en | typeof copy.sv }) {
  const [merchant, setMerchant] = useState("");
  const [description, setDescription] = useState("");
  const [accountId, setAccountId] = useState("");
  const [type, setType] = useState<Transaction["transaction_type"]>("expense");
  const [draft, setDraft] = useState({ merchant: "", description: "" });
  useEffect(() => { const timer = window.setTimeout(() => setDraft({ merchant: merchant.trim(), description: description.trim() }), 1000); return () => window.clearTimeout(timer); }, [merchant, description]);
  const predictions = useQuery({
    queryKey: ["model-lab", draft, accountId, type],
    queryFn: () => api.suggestCategories({ merchant: draft.merchant, description: draft.description || undefined, account_id: accountId ? Number(accountId) : undefined, transaction_type: type }),
    enabled: draft.merchant.length > 0,
  });
  const name = (id: number) => { const category = categories.get(id); return category?.localized_names?.[locale] ?? category?.localized_names?.en ?? category?.name ?? `#${id}`; };
  return <section className="card p-6"><p className="eyebrow">{text.lab}</p><h2>{text.lab}</h2><p className="page-subtitle mb-5">{text.labHint}</p>
    <div className="grid gap-4 sm:grid-cols-2"><label>{text.merchant}<input value={merchant} onChange={(event) => setMerchant(event.target.value)} placeholder="ICA Nära" /></label><label>{text.description} <span className="font-normal text-muted">({text.optional})</span><input value={description} onChange={(event) => setDescription(event.target.value)} /></label><label>{text.account}<select value={accountId} onChange={(event) => setAccountId(event.target.value)}><option value="">{text.allAccounts}</option>{accounts.map((account) => <option value={account.id} key={account.id}>{account.name}</option>)}</select></label><label>{text.type}<select value={type} onChange={(event) => setType(event.target.value as Transaction["transaction_type"])}>{transactionTypes.map((item) => <option key={item}>{item}</option>)}</select></label></div>
    <div className="mt-6 min-h-28 rounded-xl border border-[#dce8df] bg-[#f8fbf8] p-4">{!merchant.trim() ? <p className="text-sm text-muted">{text.waiting}</p> : predictions.isFetching ? <p className="text-sm text-muted">{text.thinking}</p> : !predictions.data?.length ? <p className="text-sm text-muted">{text.noSuggestion}</p> : <div className="space-y-4">{predictions.data.map((prediction, index) => <div key={prediction.category_id}><div className="mb-1 flex justify-between text-sm"><strong>{name(prediction.category_id)}</strong><span>{(prediction.confidence * 100).toFixed(1)}%</span></div><div className="h-2 rounded-full bg-[#e4ece6]"><div className="h-2 rounded-full" style={{ width: `${prediction.confidence * 100}%`, backgroundColor: palette[index % palette.length] }} /></div><p className="mt-1 text-xs text-muted">{prediction.reason}</p></div>)}</div>}</div>
  </section>;
}

function ScoringCard({ model, text }: { model: NonNullable<Awaited<ReturnType<typeof api.getLearningModel>>>; text: typeof copy.en | typeof copy.sv }) {
  return <section className="card p-6"><p className="eyebrow">{text.scoring}</p><h2>{text.scoring}</h2><div className="mt-5 space-y-3">{Object.entries(model.scoring.signal_weights).map(([key, value]) => <div className="flex items-center justify-between rounded-xl bg-[#f4f8f4] px-4 py-3" key={key}><code className="text-xs text-[#45655a]">{key}</code><strong>{value.toFixed(2)}×</strong></div>)}</div><div className="mt-5 grid grid-cols-2 gap-3"><div className="rounded-xl bg-[#173a32] p-4 text-white"><small className="block text-[#b7d8c5]">{text.accountBoost}</small><strong className="mt-1 block text-2xl">{model.scoring.account_multiplier.toFixed(2)}×</strong></div><div className="rounded-xl bg-[#e9f2eb] p-4 text-forest"><small className="block">{text.fuzzy}</small><strong className="mt-1 block text-2xl">{Math.round(model.scoring.similarity_threshold * 100)}%</strong></div></div></section>;
}
