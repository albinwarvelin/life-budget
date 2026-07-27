import { ExplorerPattern } from "./api";

export type TargetEvidenceProbability = {
  targetKey: string;
  weight: number;
  probability: number;
  observations: number;
};

/** Normalize one feature's stored connections for any explorer model. */
export function calculateTargetProbabilities(
  patterns: ExplorerPattern[],
  patternType: string,
  patternText: string,
): TargetEvidenceProbability[] {
  const totals = new Map<string, { weight: number; observations: number }>();
  for (const pattern of patterns) {
    if (pattern.pattern_type !== patternType || pattern.pattern_text !== patternText) continue;
    const current = totals.get(pattern.target_key) ?? { weight: 0, observations: 0 };
    current.weight += pattern.weight;
    current.observations += pattern.observations;
    totals.set(pattern.target_key, current);
  }
  const totalWeight = [...totals.values()].reduce((sum, item) => sum + item.weight, 0);
  return [...totals.entries()]
    .map(([targetKey, item]) => ({
      targetKey,
      weight: item.weight,
      observations: item.observations,
      probability: totalWeight ? item.weight / totalWeight : 0,
    }))
    .sort((left, right) => right.probability - left.probability);
}
