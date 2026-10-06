import { describe, expect, it } from "vitest";

import { illustrativeProbabilities } from "./probability-demo";

describe("synthetic temperature illustration", () => {
  it("keeps the winner while moving probabilities toward uniform as temperature increases", () => {
    const sharp = illustrativeProbabilities([3, 1, -1], 0.75);
    const soft = illustrativeProbabilities([3, 1, -1], 2);
    expect(sharp[0]).toBeGreaterThan(soft[0]);
    expect(soft[2]).toBeGreaterThan(sharp[2]);
    expect(soft[0]).toBeGreaterThan(soft[1]);
    expect(soft.reduce((sum, value) => sum + value, 0)).toBeCloseTo(1);
  });

  it("is invariant to a shared score offset and handles very large scores", () => {
    expect(illustrativeProbabilities([10003, 10001, 9999], 1)).toEqual(illustrativeProbabilities([3, 1, -1], 1));
    expect(illustrativeProbabilities([1e300, 1e300], 1)).toEqual([0.5, 0.5]);
  });

  it("rejects invalid temperatures rather than displaying NaN as confidence", () => {
    expect(() => illustrativeProbabilities([1, 0], 0)).toThrow(RangeError);
    expect(() => illustrativeProbabilities([Infinity], 1)).toThrow(RangeError);
    expect(illustrativeProbabilities([], 1)).toEqual([]);
  });
});
