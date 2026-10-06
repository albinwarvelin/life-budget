import { useState } from "react";

import { useI18n } from "../../lib/i18n";
import { illustrativeProbabilities } from "./probability-demo";

const copy = {
  en: {
    title: "When does a score become a suggestion?", badge: "Synthetic experiment",
    intro: "Three invented labels, fixed scores. Move the controls to see how probability and the suggestion decision differ.",
    temperature: "Temperature", threshold: "Suggestion threshold", support: "Reviewed examples for the leading label",
    suggested: "Leading label would be suggested", review: "Alternatives only · review required",
    thresholdReason: "The leading probability is below the threshold.", supportReason: "There are too few reviewed examples for this label.",
    passReason: "Both the probability threshold and example support pass. Confirmation is still required.",
    minimum: "Minimum support", reset: "Reset", footer: "This illustration does not change or retrain your model. Temperature reshapes scores; C changes learned coefficients and requires retraining.",
    labels: ["Label A", "Label B", "Label C"],
  },
  sv: {
    title: "När blir en poäng ett förslag?", badge: "Syntetiskt experiment",
    intro: "Tre påhittade etiketter, fasta poäng. Flytta reglagen för att se skillnaden mellan sannolikhet och beslutet att föreslå.",
    temperature: "Temperatur", threshold: "Förslagströskel", support: "Granskade exempel för den ledande etiketten",
    suggested: "Den ledande etiketten skulle föreslås", review: "Endast alternativ · granskning krävs",
    thresholdReason: "Den ledande sannolikheten ligger under tröskeln.", supportReason: "Det finns för få granskade exempel för etiketten.",
    passReason: "Både sannolikhetströskeln och antalet exempel räcker. Bekräftelse krävs fortfarande.",
    minimum: "Minsta underlag", reset: "Återställ", footer: "Illustrationen ändrar eller tränar inte modellen. Temperatur formar om poängen; C ändrar inlärda koefficienter och kräver omträning.",
    labels: ["Etikett A", "Etikett B", "Etikett C"],
  },
};

export function ProbabilityPlayground({ minimumSupport }: { minimumSupport: number }) {
  const { locale } = useI18n();
  const c = copy[locale];
  const [temperature, setTemperature] = useState(1);
  const [threshold, setThreshold] = useState(0.8);
  const [support, setSupport] = useState(8);
  const probabilities = illustrativeProbabilities([3, 1, -1], temperature);
  // These are invented competing labels. The real model also checks currency,
  // available classes and active categories; the tester below uses that API.
  const accepted = probabilities[0] >= threshold && support >= minimumSupport;
  const reason = support < minimumSupport ? c.supportReason : probabilities[0] < threshold ? c.thresholdReason : c.passReason;

  return <section className="card lab-playground">
    <div className="lab-section-heading"><span className="lab-kicker">{c.badge}</span><button className="lab-text-button" onClick={() => { setTemperature(1); setThreshold(0.8); setSupport(8); }}>{c.reset}</button></div>
    <h2>{c.title}</h2><p className="lab-help">{c.intro}</p>
    <div className="lab-bars" aria-live="polite">
      {probabilities.map((probability, index) => <div key={index}>
        <div className="lab-bar-label"><span>{c.labels[index]}</span><strong>{(probability * 100).toFixed(1)}%</strong></div>
        <div className="lab-bar-track" aria-hidden="true"><div style={{ width: `${probability * 100}%` }} className={index === 0 ? "lab-bar-fill" : "lab-bar-fill lab-bar-secondary"} /><span className="lab-threshold-marker" style={{ left: `${threshold * 100}%` }} /></div>
      </div>)}
    </div>
    <label className="lab-slider-label" htmlFor="lab-temperature"><span>{c.temperature}</span><output>{temperature.toFixed(2)}</output></label>
    <input id="lab-temperature" className="lab-slider" type="range" min="0.5" max="3" step="0.05" value={temperature} onChange={event => setTemperature(Number(event.target.value))} />
    <label className="lab-slider-label" htmlFor="lab-threshold"><span>{c.threshold}</span><output>{Math.round(threshold * 100)}%</output></label>
    <input id="lab-threshold" className="lab-slider" type="range" min="0.4" max="1" step="0.01" value={threshold} onChange={event => setThreshold(Number(event.target.value))} />
    <label className="lab-slider-label" htmlFor="lab-support"><span>{c.support}</span><output>{support}</output></label>
    <input id="lab-support" className="lab-slider" type="range" min="0" max={Math.max(20, minimumSupport)} step="1" value={support} onChange={event => setSupport(Number(event.target.value))} />
    <p className="lab-help">{c.minimum}: {minimumSupport}</p>
    <div className={`lab-decision ${accepted ? "lab-decision-pass" : "lab-decision-review"}`} role="status"><strong>{accepted ? c.suggested : c.review}</strong><p>{reason}</p></div>
    <p className="lab-footnote">{c.footer}</p>
  </section>;
}
