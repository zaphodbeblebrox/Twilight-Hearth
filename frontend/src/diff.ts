import type { Content } from "./api";

export type Change = { label: string; before: string; after: string };

function lines(content: Content): Map<string, [label: string, text: string]> {
  const out = new Map<string, [string, string]>();
  const add = (key: string, label: string, value: unknown) => {
    if (value !== null && value !== undefined && value !== "") out.set(key, [label, String(value)]);
  };
  add("field:title", "Title", content.title);
  add("field:description", "Description", content.description);
  add("field:servings", "Servings", content.servings);
  add("field:yield", "Makes", content.yield_note);
  add("field:prep", "Prep minutes", content.prep_minutes);
  add("field:cook", "Cook minutes", content.cook_minutes);
  add("field:tags", "Tags", content.tags?.join(", "));
  add("field:image", "Photo", content.image_id ? `Photo ${content.image_id.slice(0, 8)}` : "");
  add("field:source", "Source", [content.source_name, content.source_url].filter(Boolean).join(" "));
  for (const group of content.ingredient_groups ?? []) {
    add(group.id, "Ingredient group", group.name);
    for (const item of group.items ?? []) add(item.id, "Ingredient", item.text);
  }
  for (const step of content.steps ?? []) add(step.id, "Step", step.text);
  add("field:notes", "Notes", content.notes);
  return out;
}

const ingredientOrder = (c: Content) =>
  (c.ingredient_groups ?? []).flatMap((g) => (g.items ?? []).map((i) => i.id));
const stepOrder = (c: Content) => (c.steps ?? []).map((s) => s.id);

/** Items keep their ids across versions and forks, so edits can be told from replacements. */
export function diff(before: Content, after: Content): Change[] {
  const a = lines(before);
  const b = lines(after);
  const changes: Change[] = [];
  for (const key of new Set([...a.keys(), ...b.keys()])) {
    const x = a.get(key);
    const y = b.get(key);
    if (x?.[1] !== y?.[1]) {
      changes.push({ label: (y ?? x)![0], before: x?.[1] ?? "", after: y?.[1] ?? "" });
    }
  }
  for (const [kind, order] of [["ingredients", ingredientOrder], ["steps", stepOrder]] as const) {
    const x = order(before);
    const y = order(after);
    const moved = x.filter((id) => y.includes(id)).join() !== y.filter((id) => x.includes(id)).join();
    if (moved) changes.push({ label: `Order of ${kind}`, before: "", after: "Reordered" });
  }
  return changes;
}
