import { formatPrice } from "./lib";

export function label(cents: number): string {
  return `Total: ${formatPrice(cents)}`;
}
