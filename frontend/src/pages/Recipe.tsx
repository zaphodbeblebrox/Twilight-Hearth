import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { api, imageUrl, useApi, type Comment, type Me, type Recipe, type Summary } from "../api";
import { Problem } from "../components";
import { minutes, scaled } from "../quantity";

export function RecipeView({ me }: { me: Me }) {
  const { id } = useParams();
  const recipe = useApi<Recipe>(`recipes/${id}`);
  if (recipe.error) return <Problem error={recipe.error} />;
  if (!recipe.data) return null;
  return <Loaded key={id} recipe={recipe.data} me={me} />;
}

function Loaded({ recipe, me }: { recipe: Recipe; me: Me }) {
  const client = useQueryClient();
  const navigate = useNavigate();
  const [factor, setFactor] = useState(1);
  const [done, setDone] = useState<string[]>([]);
  const path = `recipes/${recipe.id}`;
  const content = recipe.content;

  const act = useMutation({
    mutationFn: (run: () => Promise<unknown>) => run(),
    onSuccess: () => client.invalidateQueries(),
  });

  function fork() {
    act.mutate(async () => {
      const copy = await api<Recipe>(`${path}/fork`, "POST");
      navigate(`/recipe/${copy.id}/edit`);
    });
  }

  function remove() {
    if (!window.confirm("Delete this recipe? Forks of it will remain.")) return;
    act.mutate(async () => {
      await api(path, "DELETE");
      navigate("/");
    });
  }

  function toggleVisibility() {
    const visibility = recipe.visibility === "private" ? "members" : "private";
    if (visibility === "members" && !window.confirm("Share with all members? They will also see its earlier versions.")) return;
    act.mutate(() => api(`${path}/visibility`, "PUT", { visibility }));
  }

  const toggle = (item: string) =>
    setDone(done.includes(item) ? done.filter((d) => d !== item) : [...done, item]);

  return (
    <article>
      <div className="no-print mb-4 flex flex-wrap gap-2">
        <button className="btn" onClick={() => act.mutate(() => api(`${path}/favorite`, recipe.is_favorite ? "DELETE" : "PUT"))}>
          {recipe.is_favorite ? "♥ Saved" : "♡ Save"}
        </button>
        <button className="btn" disabled={act.isPending} onClick={fork}>Fork{recipe.fork_count ? ` (${recipe.fork_count})` : ""}</button>
        <Link className="btn" to={`/recipe/${recipe.id}/history`}>History ({recipe.current_number})</Link>
        <button className="btn" onClick={() => window.print()}>Print</button>
        {recipe.can_edit && (
          <>
            <Link className="btn" to={`/recipe/${recipe.id}/edit`}>Edit</Link>
            <button className="btn" onClick={toggleVisibility}>{recipe.visibility === "private" ? "Share with members" : "Make private"}</button>
            <button className="btn text-red-700" onClick={remove}>Delete</button>
          </>
        )}
      </div>
      <Problem error={act.error} />

      <h1 className="text-4xl">{recipe.title}</h1>
      <p className="mt-1 text-dusk-500">
        By <Link className="link" to={`/cook/${recipe.owner.id}`}>{recipe.owner.display_name}</Link>
        {recipe.rating ? ` · ★ ${recipe.rating} (${recipe.rating_count})` : ""}
        {recipe.visibility === "private" ? " · Private" : ""}
      </p>
      <Credits recipe={recipe} />
      {recipe.image_id && <img src={imageUrl(recipe.image_id)} alt={recipe.title} className="mt-4 max-h-96 w-full rounded-xl object-cover" />}
      {content.description && <p className="mt-4 whitespace-pre-line text-lg">{content.description}</p>}

      <dl className="mt-4 flex flex-wrap gap-x-8 gap-y-2">
        <Fact label="Prep" value={content.prep_minutes != null && minutes(content.prep_minutes)} />
        <Fact label="Cook" value={content.cook_minutes != null && minutes(content.cook_minutes)} />
        <Fact label="Total" value={recipe.total_minutes != null && minutes(recipe.total_minutes)} />
        <Fact label="Servings" value={content.servings && String(Number((content.servings * factor).toFixed(1)))} />
        <Fact label="Makes" value={factor === 1 && content.yield_note} />
      </dl>

      <div className="mt-6 grid gap-8 md:grid-cols-[2fr_3fr]">
        <section>
          <div className="flex items-center justify-between">
            <h2 className="text-2xl">Ingredients</h2>
            <div className="no-print flex gap-1" role="group" aria-label="Scale recipe">
              {[0.5, 1, 2, 3].map((n) => (
                <button key={n} aria-pressed={factor === n} onClick={() => setFactor(n)} className={`rounded px-2 py-1 text-sm ${factor === n ? "bg-dusk-700 text-white" : "bg-dusk-100"}`}>
                  {n === 0.5 ? "½" : n}×
                </button>
              ))}
            </div>
          </div>
          {content.ingredient_groups?.map((group) => (
            <div key={group.id} className="mt-3">
              {group.name && <h3 className="font-semibold">{group.name}</h3>}
              <ul>
                {group.items?.map((item) => (
                  <li key={item.id}>
                    <label className="flex gap-2 py-1">
                      <input type="checkbox" checked={done.includes(item.id)} onChange={() => toggle(item.id)} />
                      <span className={done.includes(item.id) ? "text-dusk-500 line-through" : ""}>{scaled(item, factor)}</span>
                    </label>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </section>
        <section>
          <h2 className="text-2xl">Method</h2>
          <ol className="mt-3 list-decimal space-y-3 pl-6">
            {content.steps?.map((step) => <li key={step.id} className="whitespace-pre-line">{step.text}</li>)}
          </ol>
          {content.notes && (
            <>
              <h2 className="mt-6 text-2xl">Notes</h2>
              <p className="mt-2 whitespace-pre-line">{content.notes}</p>
            </>
          )}
        </section>
      </div>

      <p className="no-print mt-6 flex flex-wrap gap-2">
        {recipe.tags.map((tag) => (
          <Link key={tag} to={`/?tag=${encodeURIComponent(tag)}`} className="rounded-full bg-dusk-100 px-3 py-1 text-sm">{tag}</Link>
        ))}
      </p>

      <div className="no-print">
        {recipe.fork_count > 0 && <Forks id={recipe.id} />}
        <section className="mt-8">
          <h2 className="text-2xl">Your rating</h2>
          <div className="mt-1 text-3xl text-ember-500">
            {[1, 2, 3, 4, 5].map((stars) => (
              <button key={stars} aria-label={`${stars} star${stars > 1 ? "s" : ""}`} aria-pressed={recipe.my_rating === stars} onClick={() => act.mutate(() => api(`${path}/rating`, "PUT", { stars }))}>
                {stars <= (recipe.my_rating ?? 0) ? "★" : "☆"}
              </button>
            ))}
          </div>
        </section>
        <Comments recipe={recipe} me={me} />
      </div>
    </article>
  );
}

function Fact({ label, value }: { label: string; value: string | false | null | 0 | undefined }) {
  if (!value) return null;
  return (
    <div>
      <dt className="text-sm text-dusk-500">{label}</dt>
      <dd className="font-medium">{value}</dd>
    </div>
  );
}

/** Where this recipe came from: forks first, then any source outside the site. */
function Credits({ recipe }: { recipe: Recipe }) {
  const { source_name, source_url } = recipe.content;
  return (
    <div className="mt-2 text-sm">
      {recipe.sources.map((source, index) => (
        <p key={index}>
          {index === 0 ? "Forked from " : "which was forked from "}
          {source.available ? (
            <>
              <Link className="link" to={`/recipe/${source.recipe_id}`}>{source.title}</Link>
              {" by "}
              <Link className="link" to={`/cook/${source.owner.id}`}>{source.owner.display_name}</Link>
              {` (version ${source.number})`}
              {index === 0 && <> · <Link className="link no-print" to={`/recipe/${recipe.id}/history?source=1`}>What changed?</Link></>}
            </>
          ) : (
            `a recipe by ${source.owner.display_name} that is no longer shared`
          )}
        </p>
      ))}
      {(source_name || source_url) && (
        <p>
          Original source:{" "}
          {source_url ? (
            <a className="link break-words" href={source_url} rel="noopener noreferrer nofollow" target="_blank">{source_name || source_url}</a>
          ) : (
            source_name
          )}
        </p>
      )}
    </div>
  );
}

function Forks({ id }: { id: string }) {
  const forks = useApi<Summary[]>(`recipes/${id}/forks`);
  return (
    <section className="mt-8">
      <h2 className="text-2xl">Forks</h2>
      <ul className="mt-2 space-y-1">
        {forks.data?.map((fork) => (
          <li key={fork.id}>
            <Link className="link" to={`/recipe/${fork.id}`}>{fork.title}</Link> by {fork.owner.display_name}
          </li>
        ))}
      </ul>
    </section>
  );
}

function Comments({ recipe, me }: { recipe: Recipe; me: Me }) {
  const client = useQueryClient();
  const path = `recipes/${recipe.id}/comments`;
  const comments = useApi<Comment[]>(path);
  const [body, setBody] = useState("");
  const change = useMutation({
    mutationFn: (run: () => Promise<unknown>) => run(),
    onSuccess: () => client.invalidateQueries({ queryKey: [path] }),
  });

  function post(event: React.FormEvent) {
    event.preventDefault();
    change.mutate(async () => {
      await api(path, "POST", { body });
      setBody("");
    });
  }

  return (
    <section className="mt-8">
      <h2 className="text-2xl">Comments</h2>
      <Problem error={comments.error ?? change.error} />
      <ul className="mt-3 space-y-3">
        {comments.data?.map((comment) => (
          <li key={comment.id} className="card p-3">
            <p className="text-sm text-dusk-500">
              {comment.author.display_name} · {new Date(comment.created_at).toLocaleDateString()}
              {(comment.author.id === me.id || recipe.can_edit || me.is_admin) && (
                <> · <button className="link" onClick={() => change.mutate(() => api(`${path}/${comment.id}`, "DELETE"))}>Delete</button></>
              )}
            </p>
            <p className="whitespace-pre-line">{comment.body}</p>
          </li>
        ))}
      </ul>
      <form onSubmit={post} className="mt-3">
        <label className="label" htmlFor="comment">Add a comment</label>
        <textarea id="comment" className="field" rows={3} maxLength={5000} required value={body} onChange={(e) => setBody(e.target.value)} />
        <button className="btn-primary mt-2" disabled={change.isPending}>Post</button>
      </form>
    </section>
  );
}
