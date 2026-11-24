import type { components } from "./schema";

type Ingredient = components["schemas"]["Ingredient"];

const FRACTIONS: [number, string][] = [
  [1 / 8, "⅛"], [1 / 4, "¼"], [1 / 3, "⅓"], [3 / 8, "⅜"], [1 / 2, "½"],
  [5 / 8, "⅝"], [2 / 3, "⅔"], [3 / 4, "¾"], [7 / 8, "⅞"],
];
const METRIC = ["gram", "kilogram", "milliliter", "liter"];
const SHORT: Record<string, string> = {
  teaspoon: "tsp", tablespoon: "tbsp", ounce: "oz", pound: "lb",
  gram: "g", kilogram: "kg", milliliter: "ml", liter: "l",
};

function toNumber(quantity: string): number {
  const [top, bottom = "1"] = quantity.split("/");
  return Number(top) / Number(bottom);
}

function show(value: number, metric: boolean): string {
  if (metric) return String(Number(value.toFixed(2)));
  const whole = Math.floor(value + 0.02);
  const rest = value - whole;
  if (Math.abs(rest) < 0.02 && whole > 0) return String(whole);
  const match = FRACTIONS.find(([amount]) => Math.abs(amount - rest) < 0.02);
  if (match) return whole ? `${whole}${match[1]}` : match[1];
  return String(Number(value.toFixed(2)));
}

export function scaled(item: Ingredient, factor: number): string {
  if (factor === 1 || !item.quantity) return item.text;
  const metric = METRIC.includes(item.unit ?? "");
  const low = toNumber(item.quantity) * factor;
  const high = item.quantity_max ? toNumber(item.quantity_max) * factor : null;
  let unit = item.unit ?? "";
  if (SHORT[unit]) unit = SHORT[unit];
  else if (unit && (high ?? low) > 1.02) unit += /(ch|sh)$/.test(unit) ? "es" : "s";
  const amount = show(low, metric) + (high !== null ? `–${show(high, metric)}` : "");
  return [amount, unit, item.food].filter(Boolean).join(" ");
}

export function minutes(total: number): string {
  const hours = Math.floor(total / 60);
  const rest = total % 60;
  return [hours && `${hours} hr`, (rest || !hours) && `${rest} min`].filter(Boolean).join(" ");
}
