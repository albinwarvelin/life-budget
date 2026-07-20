import { describe, expect, it } from "vitest";
import { getClipboardImage } from "./clipboard-image";

describe("getClipboardImage", () => {
  it("returns the first image and ignores text clipboard items", () => {
    const file = new File(["image"], "capture.png", { type: "image/png" });
    const textItem = { kind: "string", type: "text/plain", getAsFile: () => null } as unknown as DataTransferItem;
    const imageItem = { kind: "file", type: "image/png", getAsFile: () => file } as unknown as DataTransferItem;
    const clipboardItems = {
      length: 2,
      0: textItem,
      1: imageItem,
    } as unknown as DataTransferItemList;

    expect(getClipboardImage(clipboardItems)).toBe(file);
  });

  it("returns null when the clipboard has no images", () => {
    const clipboardItems = {
      length: 0,
    } as unknown as DataTransferItemList;

    expect(getClipboardImage(clipboardItems)).toBeNull();
  });
});
