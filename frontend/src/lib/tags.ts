/**
 * The tag that colors a field on the map: plain labels such as "casa" before key:value tags,
 * then alphabetical (docs/01-product.md#tags-and-colors). The API lists tags in the same order.
 */
export function leadingTag(tags: string[]): string | undefined {
  return [...tags].sort(
    (a, b) =>
      Number(a.includes(":")) - Number(b.includes(":")) ||
      a.localeCompare(b, undefined, { sensitivity: "base" }),
  )[0];
}
