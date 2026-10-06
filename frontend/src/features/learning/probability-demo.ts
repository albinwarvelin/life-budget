/** Stable softmax for the synthetic lab illustration, never for saved predictions. */
export function illustrativeProbabilities(logits: readonly number[], temperature: number): number[] {
  if (!Number.isFinite(temperature) || temperature <= 0 || logits.some(value => !Number.isFinite(value))) {
    throw new RangeError("Finite logits and a positive temperature are required.");
  }
  if (!logits.length) return [];
  // Subtract before dividing so very large finite scores remain numerically safe.
  const maximum = Math.max(...logits);
  const weights = logits.map(value => Math.exp((value - maximum) / temperature));
  const total = weights.reduce((sum, value) => sum + value, 0);
  return weights.map(value => value / total);
}
