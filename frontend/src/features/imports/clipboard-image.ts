/** Return the first image available in a paste operation. */
export function getClipboardImage(items: DataTransferItemList): File | null {
  for (let index = 0; index < items.length; index += 1) {
    const item = items[index];
    if (item?.kind === "file" && item.type.startsWith("image/")) {
      return item.getAsFile();
    }
  }
  return null;
}
