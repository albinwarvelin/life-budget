import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { api, LearningModelKind, LearningModelStatus } from "../../lib/api";
import { useI18n } from "../../lib/i18n";
import { ModelEvaluation } from "./ModelEvaluation";
import { PredictionTester } from "./PredictionTester";
import { ProbabilityPlayground } from "./ProbabilityPlayground";

const kinds: LearningModelKind[] = ["type", "category", "description"];
const copy = {
  en: {
    title: "Inside the learning model", subtitle: "Follow the evidence. Explore the uncertainty. See what your reviewed transactions teach the model.",
    badge: "Experimental model lab", local: "Runs locally", back: "Settings", loading: "Loading the current model…", refresh: "Refresh status",
    retrain: "Retrain model", training: "Training model…", stale: "Reviewed changes are waiting for training", fresh: "Model is up to date", noModel: "Not trained yet", lifecycle: "Opening or refreshing this page never retrains. Predictions reuse the active model until you retrain; the first prediction can initialize a missing model.", changes: "changed transactions", versionChange: "A model update or initial training is needed.", context: "Category probabilities → description (limited influence)", blend: "Selected category blend cap", bounded: "Direct + category context",
    reviewed: "Reviewed transactions", pending: "Sync queue", snapshot: "Active snapshot", updated: "Built",
    flow: "From transaction to suggestion", flowHint: "Select a stage to inspect what happens. Each output makes its own decision about whether there is enough evidence.",
    stages: ["Observe", "Encode", "Predict", "Review"],
    steps: [
      { title: "Start with what was observed", body: "The model uses merchant or person, signed amount, currency and account. Direction means money coming in, going out, zero, or an unknown original sign. A positive amount does not automatically mean salary.", formula: "x = merchant + |amount| + direction + currency + account", note: "Description is a reviewed target to learn, not an OCR input to this predictor. Date is preserved for the transaction but is not a model feature." },
      { title: "Turn evidence into shared features", body: "Word and character fragments capture repeated names and spelling patterns. Smooth amount features let nearby amounts share evidence within the same currency and direction. Name shape is a weak clue learned alongside other features.", formula: "amount basis = exp(−½ ((log(1 + |amount|) − centre) / width)²)", note: "There is no hardcoded rule that a person sending 50 NOK must mean Car. The reviewed examples determine the learned associations." },
      { title: "Direct evidence with limited category context", body: "Category averages over possible types. Description blends a direct transaction expert with a category-conditioned expert, averaged over every possible category. Uncertain categories contribute less. The blend cap is selected on validation and cannot exceed 50%.", formula: "P(description | x) = (1 − w) Pdirect + w Σcategory P(category | x) Pcontext(description | x, category)", note: "Category is useful context, not a confirmed fact. Its weight falls with category uncertainty; unsupported categories fall back to direct evidence. Context is enabled only when validation improves log loss without reducing top-one accuracy." },
      { title: "Review closes the learning loop", body: "Each output must pass its own probability threshold and minimum example support. Uncertain candidates remain alternatives. Only confirmed transactions become training examples; later edits and deletions update that example instead of accumulating extra votes.", formula: "suggest if probability ≥ threshold and reviewed support ≥ minimum", note: "Every import still needs confirmation. The experiment and transaction tester on this page do not save records or provide training feedback." },
    ],
    observed: "Observed fields", features: "Shared features", type: "Type", category: "Category", description: "Description",
    independent: "Independent", mixture: "Weighted type mixture", confirmation: "Your confirmation → reviewed ledger → explicit retraining",
    settings: "Active model settings", settingsHint: "C and temperature are chosen on validation. Category and description use your configured 75% suggestion policy. Values below belong to the active snapshot.",
    labels: "Learned labels", c: "C · inverse regularization", temperature: "Temperature", directTemperature: "Direct expert temperature", threshold: "Suggestion threshold", off: "Alternatives only", calibrated: "Score temperature fitted on validation", uncalibrated: "Final scores not validation-calibrated",
    parameters: "Adjustment guide", parameterHint: "These are code settings, not live controls. A change needs a rebuild and fresh evaluation; changing feature construction also requires a new algorithm version.",
    parameter: "Control", value: "Current configuration", effect: "What it changes",
    parameterRows: [
      ["C candidates", "Lower C penalizes large coefficients more strongly. Higher C fits the reviewed examples more closely. Requires retraining."],
      ["Temperature candidates", "Higher temperature spreads probabilities; lower temperature concentrates them. Choose it on validation data."],
      ["Suggestion policy", "Type uses automatic threshold selection. Category and description use the configured review threshold, with measured precision reported rather than guaranteed."],
      ["Evidence policy", "Every winning label needs minimum support. The Wilson lower bound applies to automatic type-threshold selection, not your category/description overrides."],
      ["Text features", "Word/character fragment sizes and vocabulary limits trade detail against overfitting and model size. Requires retraining."],
      ["Amount smoothing", "More centres add detail. Wider bases let more nearby amounts share evidence. Requires retraining."],
      ["Chronological split", "Whole import groups stay together. Earlier groups train; validation selects settings; later groups test."],
      ["Description blend", "A capped, entropy-damped blend of direct and category-conditioned experts. Requires validation improvement and enough validation rows; otherwise direct evidence remains active."],
    ],
    support: "examples per label", validation: "validation examples", precision: "precision lower bound", word: "word", character: "character", centres: "centres", width: "width", train: "train", validate: "validation", test: "test",
    weights: "Current reviewed transactions each have weight 1. Repeated model testing adds no examples. Suggestion-origin weighting would need a separately evaluated training policy.",
    evaluation: "Check the evidence", evaluationHint: "Held-out evaluation, calibration bins and performance on unseen names. Expand to inspect the numbers.",
  },
  sv: {
    title: "Så fungerar inlärningsmodellen", subtitle: "Följ underlaget. Utforska osäkerheten. Se vad granskade transaktioner lär modellen.",
    badge: "Experimentellt modellabb", local: "Körs lokalt", back: "Inställningar", loading: "Läser den aktuella modellen…", refresh: "Uppdatera status",
    retrain: "Träna om modellen", training: "Tränar modellen…", stale: "Granskade ändringar väntar på träning", fresh: "Modellen är uppdaterad", noModel: "Inte tränad än", lifecycle: "Att öppna eller uppdatera sidan tränar aldrig om modellen. Förutsägelser använder den aktiva modellen tills du tränar om; den första förutsägelsen kan skapa en saknad modell.", changes: "ändrade transaktioner", versionChange: "En modelluppdatering eller första träning behövs.", context: "Kategorisannolikheter → beskrivning (begränsat inflytande)", blend: "Vald övre gräns för kategoriblandning", bounded: "Direkt + kategorikontext",
    reviewed: "Granskade transaktioner", pending: "Synkkö", snapshot: "Aktiv version", updated: "Byggd",
    flow: "Från transaktion till förslag", flowHint: "Välj ett steg för att se vad som händer. Varje utdata avgör själv om underlaget räcker.",
    stages: ["Observera", "Koda", "Förutsäg", "Granska"],
    steps: [
      { title: "Börja med det som observerats", body: "Modellen använder handlare eller person, signerat belopp, valuta och konto. Riktning betyder inkommande, utgående, noll eller okänt ursprungligt tecken. Ett positivt belopp betyder inte automatiskt lön.", formula: "x = handlare + |belopp| + riktning + valuta + konto", note: "Beskrivning är ett granskat mål att lära sig, inte OCR-indata till modellen. Datum bevaras för transaktionen men är inte en modellvariabel." },
      { title: "Gör underlaget till gemensamma variabler", body: "Ord- och teckenfragment fångar återkommande namn och stavningsmönster. Mjuka beloppsvariabler låter närliggande belopp dela underlag inom samma valuta och riktning. Namnform är en svag ledtråd som lärs tillsammans med andra variabler.", formula: "beloppsbas = exp(−½ ((log(1 + |belopp|) − centrum) / bredd)²)", note: "Ingen hårdkodad regel säger att en person som skickar 50 NOK måste betyda Bil. Granskade exempel bestämmer de inlärda sambanden." },
      { title: "Direkt underlag med begränsad kategorikontext", body: "Kategori väger ihop möjliga typer. Beskrivning blandar en direkt transaktionsexpert med en kategoriberoende expert, viktad över alla möjliga kategorier. Osäkra kategorier bidrar mindre. Gränsen väljs på valideringsdata och kan inte överstiga 50%.", formula: "P(beskrivning | x) = (1 − w) Pdirekt + w Σkategori P(kategori | x) Pkontext(beskrivning | x, kategori)", note: "Kategori är användbar kontext, inte ett bekräftat faktum. Dess vikt minskar vid osäkerhet; kategorier utan underlag använder direkt evidens. Kontext aktiveras bara om valideringen förbättrar log loss utan sämre träffsäkerhet." },
      { title: "Granskning sluter lärandets krets", body: "Varje utdata måste klara sin egen sannolikhetströskel och ha tillräckligt många granskade exempel. Osäkra kandidater visas som alternativ. Bara bekräftade transaktioner blir träningsexempel; ändringar och borttagningar uppdaterar exemplet i stället för att lägga till extra röster.", formula: "föreslå om sannolikhet ≥ tröskel och granskat underlag ≥ minimum", note: "Varje import måste fortfarande bekräftas. Experimentet och transaktionstestet på denna sida sparar inga poster och ger ingen träningsåterkoppling." },
    ],
    observed: "Observerade fält", features: "Gemensamma variabler", type: "Typ", category: "Kategori", description: "Beskrivning",
    independent: "Oberoende", mixture: "Viktad blandning av typer", confirmation: "Din bekräftelse → granskade poster → uttrycklig omträning",
    settings: "Aktiva modellinställningar", settingsHint: "C och temperatur väljs på valideringsdata. Kategori och beskrivning använder din förslagspolicy på 75%. Värdena nedan tillhör den aktiva modellen.",
    labels: "Inlärda etiketter", c: "C · invers regularisering", temperature: "Temperatur", directTemperature: "Direktexpertens temperatur", threshold: "Förslagströskel", off: "Endast alternativ", calibrated: "Poängtemperatur anpassad på valideringsdata", uncalibrated: "Slutpoängen är inte valideringskalibrerad",
    parameters: "Guide till justeringar", parameterHint: "Detta är kodinställningar, inte direktreglage. En ändring kräver ombyggnad och ny utvärdering; ändrad variabelkonstruktion kräver också en ny algoritmversion.",
    parameter: "Inställning", value: "Aktuell konfiguration", effect: "Vad den ändrar",
    parameterRows: [
      ["C-kandidater", "Lägre C straffar stora koefficienter mer. Högre C anpassar modellen mer till granskade exempel. Kräver omträning."],
      ["Temperaturkandidater", "Högre temperatur sprider sannolikheter; lägre koncentrerar dem. Väljs på valideringsdata."],
      ["Förslagspolicy", "Typ använder automatiskt tröskelval. Kategori och beskrivning använder den konfigurerade granskningströskeln, med uppmätt precision utan garanti."],
      ["Underlagskrav", "Varje vinnande etikett behöver ett minsta underlag. Wilson-gränsen gäller automatiskt typtröskelval, inte dina kategori- och beskrivningströsklar."],
      ["Textvariabler", "Storlek på ord- och teckenfragment samt ordförråd balanserar detalj mot överanpassning och modellstorlek. Kräver omträning."],
      ["Beloppsutjämning", "Fler centrum ger mer detalj. Bredare baser låter fler närliggande belopp dela underlag. Kräver omträning."],
      ["Kronologisk uppdelning", "Hela importgrupper hålls ihop. Tidiga grupper tränar; validering väljer inställningar; senare grupper testar."],
      ["Beskrivningsblandning", "Begränsad, entropidämpad blandning av direkt och kategoriberoende expert. Kräver bättre validering och tillräckligt många valideringsrader; annars används direkt underlag."],
    ],
    support: "exempel per etikett", validation: "valideringsexempel", precision: "undre precisionsgräns", word: "ord", character: "tecken", centres: "centrum", width: "bredd", train: "träning", validate: "validering", test: "test",
    weights: "Varje granskad transaktion har vikt 1. Upprepade modelltest lägger inte till exempel. Viktning efter förslagens ursprung skulle kräva en separat utvärderad träningspolicy.",
    evaluation: "Granska underlaget", evaluationHint: "Utvärdering på undanhållen data, kalibrering och resultat för nya namn. Expandera för att se siffrorna.",
  },
};

/** Values come from the training service, so the guide cannot drift from its grids. */
function ParameterGuide({ status }: { status: LearningModelStatus }) {
  const { locale } = useI18n();
  const c = copy[locale];
  const config = status.configuration;
  const values = [
    config.regularization_candidates.join(" / "), config.temperature_candidates.join(" / "),
    `${c.type}: ${config.threshold_candidates.map(value => `${Math.round(value * 100)}%`).join(" / ")}; ${c.category}: ${Math.round((config.suggestion_thresholds.category ?? 0.75) * 100)}%; ${c.description}: ${Math.round((config.suggestion_thresholds.description ?? 0.75) * 100)}%`,
    `${config.minimum_support} ${c.support} · ${config.minimum_validation_samples} ${c.validation} · ${Math.round(config.target_precision * 100)}% ${c.precision} (z = ${config.wilson_z})`,
    `${c.word}: ${config.word_ngram_range.join("–")} / ${config.word_features}; ${c.character}: ${config.character_ngram_range.join("–")} / ${config.character_features}`,
    `${config.amount_centers} ${c.centres} · ${c.width} ${config.amount_width} (log)`,
    `${Math.round(config.train_fraction * 100)}% ${c.train} / ${Math.round(config.validation_fraction * 100)}% ${c.validate} / ${Math.round((1 - config.train_fraction - config.validation_fraction) * 100)}% ${c.test}`,
    `${config.description_blend_candidates.map(value => `${Math.round(value * 100)}%`).join(" / ")} · ${config.description_context_min_rows} ${c.validation}`,
  ];
  return <details className="card lab-details">
    <summary><span>{c.parameters}</span><span className="lab-expand" aria-hidden="true">+</span></summary>
    <p className="lab-help">{c.parameterHint}</p>
    <div className="overflow-x-auto"><table className="lab-parameter-table"><thead><tr><th>{c.parameter}</th><th>{c.value}</th><th>{c.effect}</th></tr></thead><tbody>{c.parameterRows.map(([label, explanation], index) => <tr key={label}><th scope="row">{label}</th><td>{values[index]}</td><td>{explanation}</td></tr>)}</tbody></table></div>
    <p className="lab-footnote">{c.weights}</p>
  </details>;
}

export function LearningModelPage() {
  const { locale } = useI18n();
  const c = copy[locale];
  const [stage, setStage] = useState(2);
  const queryClient = useQueryClient();
  const model = useQuery({ queryKey: ["learning-model-status"], queryFn: api.getLearningModelStatus, staleTime: 0 });
  // Status reads never fit. Only this explicit mutation replaces a snapshot.
  const retrain = useMutation({ mutationFn: api.retrainLearningModels, onSuccess: data => queryClient.setQueryData(["learning-model-status"], data) });
  const selected = c.steps[stage];

  const status = model.data;
  return <main className="model-lab">
    <header className="lab-hero">
      <div className="lab-section-heading"><span className="lab-hero-badge">{c.badge}</span><Link to="/settings" className="lab-hero-link">← {c.back}</Link></div>
      <h1>{c.title}</h1><p>{c.subtitle}</p>
      <div className="lab-hero-footer"><span><span className="status-dot" />{c.local}</span><button onClick={() => model.refetch()} disabled={model.isFetching}>{model.isFetching ? c.loading : c.refresh} ↻</button></div>
    </header>
    {model.isPending && <p role="status">{c.loading}</p>}
    {model.isError && <div role="alert" className="alert error-alert">{model.error.message}<button className="secondary-button ml-3" onClick={() => model.refetch()}>{c.refresh}</button></div>}
    {retrain.isError && <div role="alert" className="alert error-alert">{retrain.error.message}</div>}
    {status && <section className="card p-5"><div className="lab-section-heading"><div><strong className="text-forest">{status.needs_retraining ? c.stale : c.fresh}</strong><p className="lab-help mb-0">{status.updates_since_training} {c.changes}{status.needs_retraining && !status.updates_since_training ? ` · ${c.versionChange}` : ""}</p></div><button className="primary-button" onClick={() => retrain.mutate()} disabled={retrain.isPending}>{retrain.isPending ? c.training : c.retrain}</button></div><p className="lab-footnote">{c.lifecycle}</p></section>}
    {status && <div className="lab-stats">
      <div><span>{c.reviewed}</span><strong>{status.reviewed_transactions.toLocaleString(locale)}</strong></div>
      <div><span>{c.pending}</span><strong>{status.pending_updates}</strong></div>
      <div><span>{c.snapshot}</span><strong className="lab-version">{status.snapshot_id == null ? c.noModel : `${status.algorithm} · #${status.snapshot_id}`}</strong></div>
      <div><span>{c.updated}</span><strong className="lab-version">{status.created_at ? new Date(`${status.created_at.replace(/Z$/, "")}Z`).toLocaleDateString(locale) : "—"}</strong></div>
    </div>}
    <div className="lab-explore-grid">
      <section className="card lab-flow">
        <span className="lab-kicker">01 / {c.flow}</span><h2>{c.flow}</h2><p className="lab-help">{c.flowHint}</p>
        <div className="lab-stages" role="group" aria-label={c.flow}>{c.stages.map((name, index) => <button key={name} aria-pressed={stage === index} onClick={() => setStage(index)}><span>{String(index + 1).padStart(2, "0")}</span>{name}</button>)}</div>
        <div className="lab-flow-diagram" aria-label={c.flow}>
          <div className="lab-flow-node">{c.observed}</div><div className="lab-flow-arrow" aria-hidden="true">↓</div><div className="lab-flow-node">{c.features}</div>
          <div className="lab-flow-branches"><div><span aria-hidden="true">↓</span><strong>{c.type}</strong><small>{c.independent}</small><span aria-hidden="true">↓</span><strong className="lab-category-node">{c.category}</strong><small>{c.mixture}</small></div><div><span aria-hidden="true">↓</span><strong>{c.description}</strong><small>{c.bounded}</small></div></div><p className="lab-footnote">{c.context}</p>
          <div className="lab-flow-feedback">{c.confirmation}</div>
        </div>
        <article className="lab-step-explanation" aria-live="polite"><h3>{selected.title}</h3><p>{selected.body}</p><code>{selected.formula}</code><p className="lab-footnote">{selected.note}</p></article>
      </section>
      <ProbabilityPlayground minimumSupport={status?.configuration.minimum_support ?? 3} />
    </div>
    {status?.snapshot_id != null && <>
      <section aria-labelledby="lab-settings-title"><div className="lab-section-heading"><div><span className="lab-kicker">02 / {c.settings}</span><h2 id="lab-settings-title">{c.settings}</h2></div></div><p className="lab-help">{c.settingsHint}</p>
        <div className="lab-heads">{kinds.map(kind => {
          const head = status.heads[kind];
          return <article className="card lab-head" key={kind}><div className="lab-section-heading"><h3>{c[kind]}</h3><span className={`lab-head-badge ${head.threshold > 1 ? "lab-head-off" : ""}`}>{head.threshold > 1 ? c.off : `${Math.round(head.threshold * 100)}%`}</span></div>
            <dl><div><dt>{c.c}</dt><dd>{head.regularization}</dd></div><div><dt>{kind === "description" ? c.directTemperature : c.temperature}</dt><dd>{head.temperature}</dd></div><div><dt>{c.labels}</dt><dd>{head.labels}</dd></div><div><dt>{c.threshold}</dt><dd>{head.threshold > 1 ? c.off : `${Math.round(head.threshold * 100)}%`}</dd></div>{kind === "description" && <div><dt>{c.blend}</dt><dd>{Math.round((status.report?.description_context_selection?.weight ?? 0) * 100)}%</dd></div>}</dl><p className="lab-footnote">{head.calibrated ? c.calibrated : c.uncalibrated}</p>
          </article>;
        })}</div>
      </section>
    </>}
    {status && <ParameterGuide status={status} />}
    <div><span className="lab-kicker">03 / {c.test}</span><PredictionTester /></div>
    {status?.report && <details className="card lab-details"><summary><span>{c.evaluation}</span><span className="lab-expand" aria-hidden="true">+</span></summary><p className="lab-help">{c.evaluationHint}</p><ModelEvaluation status={status} /></details>}
  </main>;
}
