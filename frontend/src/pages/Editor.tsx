import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useParams } from "react-router";
import { ApiError, api, imageUrl, useApi, type Content, type Recipe } from "../api";
import { Problem } from "../components";

type Row = { id: string; text: string };
type Group = { id: string; name: string; items: Row[] };
type Draft = Omit<Content, "ingredient_groups" | "steps" | "tags"> & {
  tags: string;
  ingredient_groups: Group[];
  steps: Row[];
};

const row = (text = ""): Row => ({ id: crypto.randomUUID(), text });
const group = (): Group => ({ id: crypto.randomUUID(), name: "", items: [row(), row(), row()] });

const blank = (): Draft => ({
  schema_version: 1, title: "", description: "", servings: null, yield_note: "",
  prep_minutes: null, cook_minutes: null, tags: "", image_id: null, source_name: "",
  source_url: "", ingredient_groups: [group()], steps: [row()], notes: "",
});

function toDraft(content: Recipe["content"]): Draft {
  return {
    ...blank(),
    ...content,
    tags: content.tags?.join(", ") ?? "",
    ingredient_groups: content.ingredient_groups?.map((g) => ({
      id: g.id, name: g.name ?? "", items: g.items?.map(({ id, text }) => ({ id, text })) ?? [],
    })) ?? [],
    steps: content.steps ?? [],
  };
}

function toContent(draft: Draft) {
  const filled = (rows: Row[]) => rows.filter((r) => r.text.trim());
  return {
    ...draft,
    tags: draft.tags.split(","),
    ingredient_groups: draft.ingredient_groups
      .map((g) => ({ ...g, items: filled(g.items) }))
      .filter((g) => g.items.length || g.name.trim()),
    steps: filled(draft.steps),
  };
}

export function Editor() {
  const { id } = useParams();
  const recipe = useApi<Recipe>(`recipes/${id}`, Boolean(id));
  if (!id) return <Form key="new" />;
  if (recipe.error) return <Problem error={recipe.error} />;
  if (!recipe.data) return null;
  if (!recipe.data.can_edit) return <p>Only the owner can edit this recipe. Fork it to make your own version.</p>;
  return <Form key={id} recipe={recipe.data} />;
}

function Form({ recipe }: { recipe?: Recipe }) {
  const client = useQueryClient();
  const navigate = useNavigate();
  const [draft, setDraft] = useState(() => (recipe ? toDraft(recipe.content) : blank()));
  // Fixed when editing starts, so a save over someone's newer version is caught.
  const [baseNumber] = useState(recipe?.current_number);
  const [visibility, setVisibility] = useState<"members" | "private">("members");
  const [message, setMessage] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const set = (part: Partial<Draft>) => setDraft((old) => ({ ...old, ...part }));

  async function run(work: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await work();
    } catch (problem) {
      const stale = problem instanceof ApiError && problem.status === 409;
      setError(stale ? new Error("This recipe was changed elsewhere since you started. Copy your changes, then reload the page.") : problem);
    } finally {
      setBusy(false);
    }
  }

  function save(event: React.FormEvent) {
    event.preventDefault();
    void run(async () => {
      const content = toContent(draft);
      const saved = recipe
        ? await api<Recipe>(`recipes/${recipe.id}`, "PUT", { content, message, base_number: baseNumber })
        : await api<Recipe>("recipes", "POST", { content, message, visibility });
      await client.invalidateQueries();
      navigate(`/recipe/${saved.id}`);
    });
  }

  function upload(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    void run(async () => {
      const form = new FormData();
      form.append("file", file);
      set({ image_id: (await api<{ id: string }>("images", "POST", form)).id });
    });
  }

  const number = (value: string) => (value === "" ? null : Number(value));
  const setGroup = (index: number, part: Partial<Group>) =>
    set({ ingredient_groups: draft.ingredient_groups.map((g, i) => (i === index ? { ...g, ...part } : g)) });

  return (
    <form onSubmit={save} className="mx-auto max-w-2xl space-y-5">
      <h1 className="text-3xl">{recipe ? "Edit recipe" : "New recipe"}</h1>
      {recipe?.sources[0] && (
        <p className="text-sm text-dusk-500">
          Your own copy of a recipe by {recipe.sources[0].owner.display_name}. Credit is kept automatically.
        </p>
      )}
      <Field label="Title"><input className="field" required maxLength={200} value={draft.title} onChange={(e) => set({ title: e.target.value })} /></Field>
      <Field label="Description"><textarea className="field" rows={3} value={draft.description} onChange={(e) => set({ description: e.target.value })} /></Field>

      <Field label="Photo"><input type="file" accept="image/*,.heic" onChange={upload} /></Field>
      {draft.image_id && (
        <div>
          <img src={imageUrl(draft.image_id)} alt="Recipe" className="max-h-48 rounded-lg" />
          <button type="button" className="link text-sm" onClick={() => set({ image_id: null })}>Remove photo</button>
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Field label="Servings"><input className="field" type="number" min="0.5" step="0.5" value={draft.servings ?? ""} onChange={(e) => set({ servings: number(e.target.value) })} /></Field>
        <Field label="Makes"><input className="field" placeholder="24 cookies" value={draft.yield_note} onChange={(e) => set({ yield_note: e.target.value })} /></Field>
        <Field label="Prep (min)"><input className="field" type="number" min="0" value={draft.prep_minutes ?? ""} onChange={(e) => set({ prep_minutes: number(e.target.value) })} /></Field>
        <Field label="Cook (min)"><input className="field" type="number" min="0" value={draft.cook_minutes ?? ""} onChange={(e) => set({ cook_minutes: number(e.target.value) })} /></Field>
      </div>

      <fieldset>
        <legend className="text-2xl font-display">Ingredients</legend>
        <p className="text-sm text-dusk-500">One per line. You can paste a whole list into a box.</p>
        {draft.ingredient_groups.map((g, index) => (
          <div key={g.id} className="card mt-3 p-3">
            <div className="mb-2 flex gap-2">
              <input className="field" aria-label="Group name" placeholder="Group name (optional), such as For the sauce" value={g.name} onChange={(e) => setGroup(index, { name: e.target.value })} />
              <button type="button" className="btn" onClick={() => set({ ingredient_groups: draft.ingredient_groups.filter((x) => x !== g) })}>Remove</button>
            </div>
            <Rows label="Ingredient" rows={g.items} onChange={(items) => setGroup(index, { items })} />
          </div>
        ))}
        <button type="button" className="btn mt-2" onClick={() => set({ ingredient_groups: [...draft.ingredient_groups, group()] })}>Add group</button>
      </fieldset>

      <fieldset>
        <legend className="mb-2 text-2xl font-display">Method</legend>
        <Rows label="Step" long rows={draft.steps} onChange={(steps) => set({ steps })} />
      </fieldset>

      <Field label="Notes"><textarea className="field" rows={3} value={draft.notes} onChange={(e) => set({ notes: e.target.value })} /></Field>
      <Field label="Tags (separated by commas)"><input className="field" placeholder="dinner, vegetarian" value={draft.tags} onChange={(e) => set({ tags: e.target.value })} /></Field>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Original source"><input className="field" placeholder="Grandma, or a cookbook" value={draft.source_name} onChange={(e) => set({ source_name: e.target.value })} /></Field>
        <Field label="Source link"><input className="field" type="url" placeholder="https://" value={draft.source_url} onChange={(e) => set({ source_url: e.target.value })} /></Field>
      </div>
      {recipe ? (
        <Field label="What did you change? (optional)"><input className="field" maxLength={200} value={message} onChange={(e) => setMessage(e.target.value)} /></Field>
      ) : (
        <Field label="Who can see it">
          <select className="field" value={visibility} onChange={(e) => setVisibility(e.target.value as typeof visibility)}>
            <option value="members">All members</option>
            <option value="private">Only me</option>
          </select>
        </Field>
      )}
      <Problem error={error} />
      <div className="flex gap-2">
        <button className="btn-primary" disabled={busy}>{busy ? "Working…" : "Save recipe"}</button>
        <button type="button" className="btn" onClick={() => navigate(-1)}>Cancel</button>
      </div>
    </form>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      {children}
    </label>
  );
}

function Rows({ label, rows, onChange, long }: { label: string; rows: Row[]; onChange: (rows: Row[]) => void; long?: boolean }) {
  function update(index: number, text: string) {
    onChange(rows.map((r, i) => (i === index ? { ...r, text } : r)));
  }

  function paste(event: React.ClipboardEvent, index: number) {
    const lines = event.clipboardData.getData("text").split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
    if (lines.length < 2 || rows[index].text.trim()) return;
    event.preventDefault();
    const [first, ...rest] = lines;
    onChange([...rows.slice(0, index), { ...rows[index], text: first }, ...rest.map(row), ...rows.slice(index + 1)]);
  }

  function move(index: number) {
    const next = [...rows];
    [next[index - 1], next[index]] = [next[index], next[index - 1]];
    onChange(next);
  }

  return (
    <div className="space-y-2">
      {rows.map((r, index) => {
        const props = {
          className: "field",
          "aria-label": `${label} ${index + 1}`,
          value: r.text,
          onPaste: (e: React.ClipboardEvent) => paste(e, index),
        };
        return (
          <div key={r.id} className="flex items-start gap-2">
            {long ? (
              <textarea rows={2} maxLength={5000} {...props} onChange={(e) => update(index, e.target.value)} />
            ) : (
              <input maxLength={500} {...props} onChange={(e) => update(index, e.target.value)} />
            )}
            <button type="button" className="btn" disabled={index === 0} aria-label={`Move ${label} ${index + 1} up`} onClick={() => move(index)}>↑</button>
            <button type="button" className="btn" aria-label={`Remove ${label} ${index + 1}`} onClick={() => onChange(rows.filter((x) => x !== r))}>✕</button>
          </div>
        );
      })}
      <button type="button" className="btn" onClick={() => onChange([...rows, row()])}>Add {label.toLowerCase()}</button>
    </div>
  );
}
