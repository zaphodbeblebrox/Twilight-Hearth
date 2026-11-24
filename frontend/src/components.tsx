import { Link } from "react-router";
import { imageUrl, type Summary } from "./api";
import { minutes } from "./quantity";

export function Problem({ error }: { error: unknown }) {
  if (!error) return null;
  return (
    <p role="alert" className="my-3 whitespace-pre-line rounded-lg bg-red-50 p-3 text-sm text-red-800">
      {error instanceof Error ? error.message : "Something went wrong"}
    </p>
  );
}

export function RecipeCard({ recipe }: { recipe: Summary }) {
  return (
    <article className="card overflow-hidden">
      <Link to={`/recipe/${recipe.id}`} className="block">
        {recipe.image_id ? (
          <img src={imageUrl(recipe.image_id)} alt="" loading="lazy" className="aspect-[3/2] w-full object-cover" />
        ) : (
          <div className="flex aspect-[3/2] items-center justify-center bg-dusk-100 font-display text-5xl text-dusk-500" aria-hidden>
            {recipe.title[0]}
          </div>
        )}
        <h2 className="px-4 pt-3 text-lg leading-snug">{recipe.title}</h2>
      </Link>
      <p className="px-4 pb-4 pt-1 text-sm text-dusk-500">
        <Link to={`/cook/${recipe.owner.id}`} className="hover:underline">{recipe.owner.display_name}</Link>
        {recipe.total_minutes ? ` · ${minutes(recipe.total_minutes)}` : ""}
        {recipe.rating ? ` · ★ ${recipe.rating}` : ""}
        {recipe.is_fork ? " · Fork" : ""}
        {recipe.visibility === "private" ? " · Private" : ""}
      </p>
    </article>
  );
}
