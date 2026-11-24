import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";
import { api, useApi, type Content, type Recipe, type Revision, type RevisionSummary } from "../api";
import { Problem } from "../components";
import { diff } from "../diff";

export function History() {
  const { id } = useParams();
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const client = useQueryClient();
  const recipe = useApi<Recipe>(`recipes/${id}`);
  const revisions = useApi<RevisionSummary[]>(`recipes/${id}/revisions`);
  const [error, setError] = useState<unknown>(null);

  if (recipe.error || revisions.error) return <Problem error={recipe.error ?? revisions.error} />;
  if (!recipe.data || !revisions.data) return null;

  const source = recipe.data.sources[0];
  const againstSource = params.get("source") === "1" && source?.available;
  const number = Number(params.get("v")) || recipe.data.current_number;
  const here = `recipes/${id}/revisions/${number}`;
  const before = againstSource
    ? `recipes/${source.recipe_id}/revisions/${source.number}`
    : number > 1
      ? `recipes/${id}/revisions/${number - 1}`
      : null;

  async function restore() {
    if (!window.confirm(`Restore version ${number}? This saves it as a new version.`)) return;
    try {
      await api(`recipes/${id}/restore`, "POST", { number, base_number: recipe.data!.current_number });
      await client.invalidateQueries();
      navigate(`/recipe/${id}`);
    } catch (problem) {
      setError(problem);
    }
  }

  return (
    <>
      <h1 className="text-3xl">History of <Link className="link" to={`/recipe/${id}`}>{recipe.data.title}</Link></h1>
      <Problem error={error} />
      <div className="mt-5 grid gap-6 md:grid-cols-[1fr_2fr]">
        <ol className="space-y-2">
          {revisions.data.map((revision) => (
            <li key={revision.number}>
              <button
                className={`card w-full p-3 text-left ${revision.number === number ? "border-ember-500" : ""}`}
                aria-pressed={revision.number === number}
                onClick={() => setParams({ v: String(revision.number) })}
              >
                <span className="font-medium">Version {revision.number}</span>
                {revision.message && <span className="block text-sm">{revision.message}</span>}
                <span className="block text-sm text-dusk-500">
                  {revision.author.display_name} · {new Date(revision.created_at).toLocaleString()}
                </span>
              </button>
            </li>
          ))}
        </ol>
        <section>
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-xl">
              {againstSource
                ? `Version ${number} compared with the original by ${source.owner.display_name}`
                : number > 1 ? `Changes in version ${number}` : "First version"}
            </h2>
            <span className="flex gap-2">
              {source?.available && !againstSource && (
                <button className="btn" onClick={() => setParams({ v: String(number), source: "1" })}>Compare with original</button>
              )}
              {recipe.data.can_edit && number !== recipe.data.current_number && (
                <button className="btn" onClick={restore}>Restore this version</button>
              )}
            </span>
          </div>
          <Changes before={before} after={here} />
        </section>
      </div>
    </>
  );
}

function Changes({ before, after }: { before: string | null; after: string }) {
  const a = useApi<Revision>(before ?? "", Boolean(before));
  const b = useApi<Revision>(after);
  if (a.error || b.error) return <Problem error={a.error ?? b.error} />;
  if (!b.data || (before && !a.data)) return null;
  const content = b.data.content as Content;
  const empty: Content = {
    ...content, title: "", description: "", servings: null, yield_note: "", prep_minutes: null,
    cook_minutes: null, tags: [], image_id: null, source_name: "", source_url: "",
    ingredient_groups: [], steps: [], notes: "",
  };
  const changes = diff(a.data ? (a.data.content as Content) : empty, content);
  if (!changes.length) return <p className="text-dusk-500">No differences.</p>;
  return (
    <ul className="space-y-3">
      {changes.map((change, index) => (
        <li key={index} className="card overflow-hidden">
          <p className="px-3 pt-2 text-sm text-dusk-500">{change.label}</p>
          {change.before && <p className="whitespace-pre-line bg-red-50 px-3 py-1 text-red-900"><del className="no-underline">− {change.before}</del></p>}
          {change.after && <p className="whitespace-pre-line bg-green-50 px-3 py-1 text-green-900"><ins className="no-underline">+ {change.after}</ins></p>}
        </li>
      ))}
    </ul>
  );
}
