import { describe, expect, it } from "vitest";

import { ExplorerPattern, LearningPattern } from "./api";
import { calculateEvidenceProbabilities, calculateTargetProbabilities } from "./learning-model";

const connection = (category_id: number, weight: number): LearningPattern => ({
  id: category_id,
  pattern_type: "merchant_token",
  pattern_text: "ica",
  category_id,
  account_id: null,
  transaction_type: "expense",
  weight,
  observations: 1,
});

describe("calculateTargetProbabilities", () => {
  it("supports category, type, and description graph targets", () => {
    const patterns: ExplorerPattern[] = [
      { id: 1, pattern_type: "amount_band", pattern_text: "SEK:0-49", target_key: "Coffee", weight: 3, observations: 2, account_id: null, transaction_type: null, category_id: null },
      { id: 2, pattern_type: "amount_band", pattern_text: "SEK:0-49", target_key: "Fuel", weight: 1, observations: 1, account_id: null, transaction_type: null, category_id: null },
    ];

    expect(calculateTargetProbabilities(patterns, "amount_band", "SEK:0-49"))
      .toMatchObject([{ targetKey: "Coffee", probability: 0.75 }, { targetKey: "Fuel", probability: 0.25 }]);
  });
});

describe("calculateEvidenceProbabilities", () => {
  it("normalizes the stored evidence across connected categories", () => {
    const result = calculateEvidenceProbabilities([connection(1, 3), connection(2, 1)], "merchant_token", "ica");

    expect(result.map((item) => [item.categoryId, item.probability])).toEqual([
      [1, 0.75],
      [2, 0.25],
    ]);
  });

  it("ignores other phrases and signal types", () => {
    const other = { ...connection(2, 50), pattern_text: "coop" };
    expect(calculateEvidenceProbabilities([connection(1, 2), other], "merchant_token", "ica"))
      .toHaveLength(1);
  });
});
