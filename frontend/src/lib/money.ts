/**
 * Parse the API's fixed two-decimal money strings into integer minor units.
 * Adding cents/øre as integers avoids binary floating-point drift such as
 * 0.1 + 0.2 becoming 0.30000000000000004.
 */
export function toMinorUnits(value: string): number {
  const match = /^(-?)(\d+)(?:\.(\d{1,2}))?$/.exec(value.trim());
  if (!match) throw new Error(`Invalid fixed-point amount: ${value}`);
  const magnitude = Number(match[2]) * 100 + Number((match[3] ?? "").padEnd(2, "0"));
  return match[1] ? -magnitude : magnitude;
}

export function fromMinorUnits(value: number): number {
  return value / 100;
}
