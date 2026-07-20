import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { api, ExplorerModel, LearningModelKind, Transaction } from "../../lib/api";
import { calculateTargetProbabilities } from "../../lib/learning-model";
import { useI18n } from "../../lib/i18n";
import { DescriptionPredictionTester } from "./DescriptionPredictionTester";

const palette = ["#2e6b5a", "#a86d32", "#5573a5", "#9a5274", "#6c7d32", "#7357a6"];
const transactionTypes: Transaction["transaction_type"][] = [
  "expense", "income", "reimbursement", "savings", "transfer",
];

const copy = {
  en: {
    eyebrow: "Prediction intelligence", title: "Learning model explorer",
    subtitle: "Inspect how remembered words, phrases and amount bands connect to predictions.",
    back: "Back to settings", category: "Categories", type: "Types", description: "Descriptions",
    events: "Learning events", connections: "Connections", phrases: "Stored signals", outputs: "Outputs",
    map: "Interactive connection map", mapHint: "Switch models, then select a signal or connection to inspect its evidence.",
    search: "Find a signal", allSignals: "All signal types", allAccounts: "All account scopes",
    global: "Global only", allTypes: "All transaction types", observations: "Minimum observations",
    noConnections: "No connections match these filters.", evidence: "Evidence distribution",
    choosePhrase: "Choose a signal in the map to inspect its output probabilities.", weight: "weight",
    seen: "observations", notCalibrated: "These are relative stored evidence scores, not calibrated real-world probabilities.",
    scoring: "Scoring weights", fuzzy: "Fuzzy threshold", accountBoost: "Same-account multiplier", minimumConfidence: "Minimum suggestion confidence",
    loading: "Loading model…", model: "Prediction model",
  },
  sv: {
    eyebrow: "Prediktionsintelligens", title: "Utforska inlärningsmodeller",
    subtitle: "Se hur sparade ord, fraser och beloppsintervall kopplas till förutsägelser.",
    back: "Tillbaka till inställningar", category: "Kategorier", type: "Typer", description: "Beskrivningar",
    events: "Inlärningshändelser", connections: "Kopplingar", phrases: "Sparade signaler", outputs: "Resultat",
    map: "Interaktiv kopplingskarta", mapHint: "Byt modell och välj sedan en signal eller koppling för att granska bevisen.",
    search: "Sök efter en signal", allSignals: "Alla signaltyper", allAccounts: "Alla kontoomfång",
    global: "Endast globalt", allTypes: "Alla transaktionstyper", observations: "Minsta antal observationer",
    noConnections: "Inga kopplingar matchar filtren.", evidence: "Bevisfördelning",
    choosePhrase: "Välj en signal i kartan för att se sannolikheterna för dess resultat.", weight: "vikt",
    seen: "observationer", notCalibrated: "Detta är relativa bevispoäng, inte kalibrerade verkliga sannolikheter.",
    scoring: "Poängvikter", fuzzy: "Tröskel för ungefärlig matchning", accountBoost: "Multiplikator för samma konto", minimumConfidence: "Minsta förslagskonfidens",
    loading: "Läser modellen…", model: "Prediktionsmodell",
  },
} as const;

type PhraseNode = { key: string; type: string; patternText: string; text: string; weight: number };

export function LearningModelPage() {
  const { locale } = useI18n();
  const c = copy[locale];
  const [modelKind, setModelKind] = useState<LearningModelKind>("category");
  const model = useQuery({
    queryKey: ["learning-model", modelKind],
    queryFn: () => api.getExplorerModel(modelKind),
  });
  const accounts = useQuery({ queryKey: ["accounts"], queryFn: api.listAccounts });
  const categories = useQuery({ queryKey: ["categories"], queryFn: api.listCategories });
  const [search, setSearch] = useState("");
  const [signal, setSignal] = useState("all");
  const [accountScope, setAccountScope] = useState("all");
  const [transactionType, setTransactionType] = useState("all");
  const [minimumObservations, setMinimumObservations] = useState(1);
  const [selectedPhrase, setSelectedPhrase] = useState<string | null>(null);

  useEffect(() => {
    setSelectedPhrase(null);
    setSignal("all");
  }, [modelKind]);

  const filteredPatterns = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase();
    return (model.data?.patterns ?? []).filter((pattern) =>
      (!needle || pattern.pattern_text.toLocaleLowerCase().includes(needle) ||
        (pattern.localized_display_texts?.[locale] ?? pattern.display_text ?? "").toLocaleLowerCase().includes(needle)) &&
      (signal === "all" || pattern.pattern_type === signal) &&
      (modelKind !== "category" || accountScope === "all" ||
        (accountScope === "global" ? pattern.account_id === null : pattern.account_id === Number(accountScope))) &&
      (modelKind !== "category" || transactionType === "all" || pattern.transaction_type === transactionType) &&
      pattern.observations >= minimumObservations,
    );
  }, [model.data, search, signal, modelKind, accountScope, transactionType, minimumObservations, locale]);

  const graph = useMemo(() => {
    const totals = new Map<string, PhraseNode>();
    for (const pattern of filteredPatterns) {
      const key = `${pattern.pattern_type}:${pattern.pattern_text}`;
      const displayText = pattern.localized_display_texts?.[locale] ?? pattern.display_text ?? pattern.pattern_text;
      const node = totals.get(key) ?? { key, type: pattern.pattern_type, patternText: pattern.pattern_text, text: displayText, weight: 0 };
      node.weight += pattern.weight;
      totals.set(key, node);
    }
    const phrases = [...totals.values()].sort((left, right) => right.weight - left.weight).slice(0, 24);
    const keys = new Set(phrases.map((phrase) => phrase.key));
    const edges = filteredPatterns.filter((pattern) => keys.has(`${pattern.pattern_type}:${pattern.pattern_text}`)).slice(0, 100);
    const targetKeys = [...new Set(edges.map((pattern) => pattern.target_key))];
    return { phrases, edges, targetKeys };
  }, [filteredPatterns, locale]);

  useEffect(() => {
    if (selectedPhrase && !graph.phrases.some((phrase) => phrase.key === selectedPhrase)) {
      setSelectedPhrase(null);
    }
  }, [graph.phrases, selectedPhrase]);

  if (model.isLoading) return <div className="grid min-h-[55vh] place-items-center text-muted">{c.loading}</div>;
  if (model.isError) return <div className="alert error-alert">{(model.error as Error).message}</div>;

  const data = model.data!;
  const targetMap = new Map(data.targets.map((target) => [target.key, target]));
  const targetName = (key: string) => {
    const target = targetMap.get(key);
    return target?.localized_names?.[locale] ?? target?.localized_names?.en ?? target?.label ?? key;
  };
  const selectedNode = graph.phrases.find((phrase) => phrase.key === selectedPhrase);
  const evidence = selectedNode
    ? calculateTargetProbabilities(filteredPatterns, selectedNode.type, selectedNode.patternText)
    : [];
  const signalTypes = [...new Set(data.patterns.map((pattern) => pattern.pattern_type))].sort();
  const uniquePhraseCount = new Set(data.patterns.map((pattern) => `${pattern.pattern_type}:${pattern.pattern_text}`)).size;
  const graphHeight = Math.max(500, Math.max(graph.phrases.length, graph.targetKeys.length) * 42 + 90);
  const phraseY = (index: number) => 65 + index * ((graphHeight - 120) / Math.max(graph.phrases.length - 1, 1));
  const targetY = (index: number) => 65 + index * ((graphHeight - 120) / Math.max(graph.targetKeys.length - 1, 1));

  return <div className="space-y-7">
    <header className="flex flex-wrap items-end justify-between gap-5">
      <div><p className="eyebrow">{c.eyebrow}</p><h1>{c.title}</h1><p className="page-subtitle max-w-2xl">{c.subtitle}</p></div>
      <Link className="secondary-button no-underline" to="/settings">← {c.back}</Link>
    </header>

    <div className="flex flex-wrap gap-2" role="group" aria-label={c.model}>
      {(["category", "type", "description"] as LearningModelKind[]).map((kind) =>
        <button key={kind} type="button" className={kind === modelKind ? "primary-button" : "secondary-button"} onClick={() => setModelKind(kind)}>
          {c[kind]}
        </button>)}
    </div>

    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {[[c.events, data.event_count], [c.connections, data.patterns.length], [c.phrases, uniquePhraseCount], [c.outputs, data.targets.length]].map(([label, value]) =>
        <div className="card overflow-hidden p-5" key={label}><p className="text-xs font-bold uppercase tracking-[.12em] text-[#668277]">{label}</p><strong className="mt-2 block text-3xl text-forest">{value}</strong></div>)}
    </div>

    {modelKind === "description" && <DescriptionPredictionTester categories={categories.data ?? []} locale={locale} />}

    <section className="card overflow-hidden">
      <div className="border-b border-[#e2ebe4] bg-gradient-to-r from-[#f6fbf6] to-white p-6">
        <p className="eyebrow">{c[modelKind]}</p><h2>{c.map}</h2><p className="page-subtitle">{c.mapHint}</p>
        <div className={`mt-5 grid gap-3 md:grid-cols-2 ${modelKind === "category" ? "xl:grid-cols-5" : "xl:grid-cols-3"}`}>
          <label>{c.search}<input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="ICA, coffee…" /></label>
          <label>{c.scoring}<select value={signal} onChange={(event) => setSignal(event.target.value)}><option value="all">{c.allSignals}</option>{signalTypes.map((item) => <option key={item}>{item}</option>)}</select></label>
          {modelKind === "category" && <label>{c.allAccounts}<select value={accountScope} onChange={(event) => setAccountScope(event.target.value)}><option value="all">{c.allAccounts}</option><option value="global">{c.global}</option>{accounts.data?.map((account) => <option value={account.id} key={account.id}>{account.name}</option>)}</select></label>}
          {modelKind === "category" && <label>{c.allTypes}<select value={transactionType} onChange={(event) => setTransactionType(event.target.value)}><option value="all">{c.allTypes}</option>{transactionTypes.map((item) => <option key={item}>{item}</option>)}</select></label>}
          <label>{c.observations}<input type="number" min="1" value={minimumObservations} onChange={(event) => setMinimumObservations(Math.max(1, Number(event.target.value)))} /></label>
        </div>
      </div>

      {!graph.edges.length ? <div className="p-12 text-center text-muted">{c.noConnections}</div> :
        <div className="grid xl:grid-cols-[minmax(0,1fr)_340px]">
          <div className="min-w-0 overflow-auto bg-[radial-gradient(circle_at_center,#edf4ef_1px,transparent_1px)] [background-size:22px_22px]">
            <svg className="min-w-[860px] w-full" viewBox={`0 0 1000 ${graphHeight}`} role="img" aria-label={`${c.map}: ${c[modelKind]}`}>
              <text x="70" y="28" className="fill-[#668277] text-[11px] font-bold uppercase tracking-widest">{c.phrases}</text>
              <text x="790" y="28" className="fill-[#668277] text-[11px] font-bold uppercase tracking-widest">{c.outputs}</text>
              {graph.edges.map((edge) => {
                const key = `${edge.pattern_type}:${edge.pattern_text}`;
                const left = graph.phrases.findIndex((phrase) => phrase.key === key);
                const right = graph.targetKeys.indexOf(edge.target_key);
                const focused = !selectedPhrase || selectedPhrase === key;
                const edgeLabel = edge.localized_display_texts?.[locale] ?? edge.display_text ?? edge.pattern_text;
                return <path key={edge.id} d={`M 285 ${phraseY(left)} C 470 ${phraseY(left)}, 530 ${targetY(right)}, 715 ${targetY(right)}`} fill="none" stroke={palette[right % palette.length]} strokeWidth={Math.min(8, 1 + Math.sqrt(edge.weight))} opacity={focused ? .62 : .07} className="cursor-pointer transition-opacity" onClick={() => setSelectedPhrase(key)}><title>{`${edgeLabel} → ${targetName(edge.target_key)} · ${edge.weight.toFixed(2)}`}</title></path>;
              })}
              {graph.phrases.map((phrase, index) => {
                const selected = phrase.key === selectedPhrase;
                return <g key={phrase.key} role="button" tabIndex={0} aria-label={phrase.text} className="cursor-pointer outline-none" onClick={() => setSelectedPhrase(selected ? null : phrase.key)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") setSelectedPhrase(selected ? null : phrase.key); }}>
                  <rect x="55" y={phraseY(index) - 18} width="230" height="36" rx="11" fill={selected ? "#173a32" : "white"} stroke={selected ? "#173a32" : "#cadbd0"} strokeWidth={selected ? 2 : 1} />
                  <text x="70" y={phraseY(index) + 4} fill={selected ? "white" : "#203a31"} className="text-[12px] font-semibold">{phrase.text.length > 26 ? `${phrase.text.slice(0, 25)}…` : phrase.text}</text>
                  <title>{`${phrase.type}: ${phrase.text}`}</title>
                </g>;
              })}
              {graph.targetKeys.map((key, index) => <g key={key}>
                <circle cx="735" cy={targetY(index)} r="7" fill={palette[index % palette.length]} />
                <rect x="753" y={targetY(index) - 18} width="205" height="36" rx="11" fill="white" stroke="#cadbd0" />
                <text x="769" y={targetY(index) + 4} className="fill-[#203a31] text-[12px] font-bold">{shorten(targetName(key), 25)}</text>
                <title>{targetName(key)}</title>
              </g>)}
            </svg>
          </div>
          <aside className="border-t border-[#e2ebe4] bg-[#fbfdfb] p-6 xl:border-l xl:border-t-0">
            <p className="eyebrow">{c.evidence}</p><h2 className="break-words">{selectedNode?.text ?? c.evidence}</h2><p className="page-subtitle mb-5">{selectedNode ? selectedNode.type : c.choosePhrase}</p>
            <div className="space-y-5">{evidence.map((item, index) => <div key={item.targetKey}>
              <div className="mb-1 flex items-center justify-between gap-3 text-sm"><strong>{targetName(item.targetKey)}</strong><span className="font-bold">{(item.probability * 100).toFixed(1)}%</span></div>
              <div className="h-2 overflow-hidden rounded-full bg-[#e4ece6]"><div className="h-full rounded-full transition-all duration-500" style={{ width: `${item.probability * 100}%`, backgroundColor: palette[index % palette.length] }} /></div>
              <p className="mt-1 text-xs text-muted">{item.weight.toFixed(2)} {c.weight} · {item.observations} {c.seen}</p>
            </div>)}</div>
            {selectedNode && <p className="mt-7 rounded-xl bg-[#edf5ef] p-4 text-xs leading-5 text-[#4f695f]">{c.notCalibrated}</p>}
          </aside>
        </div>}
    </section>

    <ScoringCard model={data} text={c} />
  </div>;
}

function shorten(value: string, length: number) {
  return value.length > length ? `${value.slice(0, length - 1)}…` : value;
}

function ScoringCard({ model, text }: { model: ExplorerModel; text: typeof copy.en | typeof copy.sv }) {
  return <section className="card p-6"><p className="eyebrow">{text[model.model_kind]}</p><h2>{text.scoring}</h2>
    <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{Object.entries(model.scoring.signal_weights).map(([key, value]) => <div className="flex items-center justify-between rounded-xl bg-[#f4f8f4] px-4 py-3" key={key}><code className="text-xs text-[#45655a]">{key}</code><strong>{value.toFixed(2)}×</strong></div>)}</div>
    <div className="mt-5 flex flex-wrap gap-3"><div className="rounded-xl bg-[#e9f2eb] p-4 text-forest"><small className="block">{text.fuzzy}</small><strong className="mt-1 block text-2xl">{Math.round(model.scoring.similarity_threshold * 100)}%</strong></div>{model.scoring.minimum_confidence !== null && <div className="rounded-xl bg-[#e9f2eb] p-4 text-forest"><small className="block">{text.minimumConfidence}</small><strong className="mt-1 block text-2xl">{Math.round(model.scoring.minimum_confidence * 100)}%</strong></div>}{model.scoring.account_multiplier && <div className="rounded-xl bg-[#173a32] p-4 text-white"><small className="block text-[#b7d8c5]">{text.accountBoost}</small><strong className="mt-1 block text-2xl">{model.scoring.account_multiplier.toFixed(2)}×</strong></div>}</div>
  </section>;
}
