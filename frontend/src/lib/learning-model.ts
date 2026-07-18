import { LearningPattern } from "./api";

export type EvidenceProbability = {
  categoryId: number;
  weight: number;
  probability: number;
  observations: number;
};

/**
 * Turn all stored connections for one phrase into a relative distribution.
 * This explains the model's evidence; it is not a calibrated real-world odds
 * estimate, because the learner intentionally uses transparent heuristics.
 */
export function calculateEvidenceProbabilities(
  patterns: LearningPattern[],
  patternType: string,
  patternText: string,
): EvidenceProbability[] {
  const totals = new Map<number, { weight: number; observations: number }>();

  for (const pattern of patterns) {
    if (pattern.pattern_type !== patternType || pattern.pattern_text !== patternText) continue;
    const current = totals.get(pattern.category_id) ?? { weight: 0, observations: 0 };
    current.weight += pattern.weight;
    current.observations += pattern.observations;
    totals.set(pattern.category_id, current);
  }

  const totalWeight = [...totals.values()].reduce((sum, value) => sum + value.weight, 0);
  return [...totals.entries()]
    .map(([categoryId, value]) => ({
      categoryId,
      weight: value.weight,
      observations: value.observations,
      probability: totalWeight > 0 ? value.weight / totalWeight : 0,
    }))
    .sort((left, right) => right.probability - left.probability);
}
