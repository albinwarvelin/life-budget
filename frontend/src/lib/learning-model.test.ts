import { describe, expect, it } from "vitest";

import { ExplorerPattern } from "./api";
import { calculateTargetProbabilities } from "./learning-model";

describe("calculateTargetProbabilities", () => {
  it("supports category, type, and description graph targets", () => {
    const patterns: ExplorerPattern[] = [
      { id: 1, pattern_type: "amount_band", pattern_text: "SEK:0-49", display_text: null, localized_display_texts: {}, target_key: "Coffee", weight: 3, observations: 2, account_id: null, transaction_type: null, category_id: null },
      { id: 2, pattern_type: "amount_band", pattern_text: "SEK:0-49", display_text: null, localized_display_texts: {}, target_key: "Fuel", weight: 1, observations: 1, account_id: null, transaction_type: null, category_id: null },
    ];

    expect(calculateTargetProbabilities(patterns, "amount_band", "SEK:0-49"))
      .toMatchObject([{ targetKey: "Coffee", probability: 0.75 }, { targetKey: "Fuel", probability: 0.25 }]);
  });
});
