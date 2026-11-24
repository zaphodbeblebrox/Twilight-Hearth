import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router";
import { api, useApi, type RecipePage, type Tag } from "../api";
import { Problem, RecipeCard } from "../components";

const PAGE = 24;

export function Browse({ title, filter = "" }: { title: string; filter?: string }) {
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const tag = params.get("tag") ?? "";
  const sort = params.get("sort") ?? "recent";
  const page = Math.max(1, Number(params.get("page")) || 1);

  const query = new URLSearchParams(filter);
  query.set("sort", sort);
  query.set("limit", String(PAGE));
  query.set("offset", String((page - 1) * PAGE));
  if (q) query.set("q", q);
  if (tag) query.set("tag", tag);
  const path = `recipes?${query}`;
  const recipes = useQuery({
    queryKey: [path],
    queryFn: () => api<RecipePage>(path),
    placeholderData: keepPreviousData,
  });
  const tags = useApi<Tag[]>("tags");

  function change(name: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(name, value);
    else next.delete(name);
    if (name !== "page") next.delete("page");
    setParams(next);
  }

  const pages = Math.ceil((recipes.data?.total ?? 0) / PAGE);
  return (
    <>
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <h1 className="text-3xl">{title}</h1>
        <label className="text-sm">
          Sort by{" "}
          <select className="rounded-lg border border-dusk-200 bg-white px-2 py-1" value={sort} onChange={(e) => change("sort", e.target.value)}>
            <option value="recent">Recently updated</option>
            <option value="rating">Highest rated</option>
            <option value="quick">Quickest</option>
            <option value="title">Title</option>
          </select>
        </label>
      </div>
      {q && (
        <p className="mb-3 text-sm">
          Results for “{q}” <button className="link" onClick={() => change("q", "")}>Clear</button>
        </p>
      )}
      <div className="mb-5 flex flex-wrap gap-2">
        {tags.data?.map((item) => (
          <button
            key={item.tag}
            aria-pressed={tag === item.tag}
            onClick={() => change("tag", tag === item.tag ? "" : item.tag)}
            className={`rounded-full px-3 py-1 text-sm ${tag === item.tag ? "bg-dusk-700 text-white" : "bg-dusk-100 hover:bg-dusk-200"}`}
          >
            {item.tag}
          </button>
        ))}
      </div>
      <Problem error={recipes.error} />
      {recipes.data?.items.length === 0 && <p className="text-dusk-500">No recipes here yet.</p>}
      <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
        {recipes.data?.items.map((recipe) => <RecipeCard key={recipe.id} recipe={recipe} />)}
      </div>
      {pages > 1 && (
        <div className="mt-6 flex items-center justify-center gap-4">
          <button className="btn" disabled={page <= 1} onClick={() => change("page", String(page - 1))}>Previous</button>
          <span className="text-sm">Page {page} of {pages}</span>
          <button className="btn" disabled={page >= pages} onClick={() => change("page", String(page + 1))}>Next</button>
        </div>
      )}
    </>
  );
}
