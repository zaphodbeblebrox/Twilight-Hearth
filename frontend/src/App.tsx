import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, NavLink, Route, Routes, useNavigate, useParams } from "react-router";
import { ApiError, api, useApi, type Me, type User } from "./api";
import { Problem } from "./components";
import { AdminPage } from "./pages/Admin";
import { Browse } from "./pages/Browse";
import { Editor } from "./pages/Editor";
import { History } from "./pages/History";
import { Join, Login } from "./pages/Login";
import { RecipeView } from "./pages/Recipe";

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/join" element={<Join />} />
      <Route path="*" element={<Members />} />
    </Routes>
  );
}

function Members() {
  const me = useApi<Me>("auth/me");
  if (me.error instanceof ApiError && me.error.status === 401) return <Login />;
  if (me.error) return <Problem error={me.error} />;
  if (!me.data) return null;
  return (
    <>
      <Header me={me.data} />
      <main className="mx-auto max-w-5xl px-4 py-6">
        <Routes>
          <Route path="/" element={<Browse title="Recipes" />} />
          <Route path="/saved" element={<Browse title="Saved recipes" filter="favorites=true" />} />
          <Route path="/cook/:id" element={<Profile />} />
          <Route path="/new" element={<Editor />} />
          <Route path="/recipe/:id" element={<RecipeView me={me.data} />} />
          <Route path="/recipe/:id/edit" element={<Editor />} />
          <Route path="/recipe/:id/history" element={<History />} />
          {me.data.is_admin && <Route path="/admin" element={<AdminPage me={me.data} />} />}
          <Route path="*" element={<p>That page does not exist.</p>} />
        </Routes>
      </main>
    </>
  );
}

function Header({ me }: { me: Me }) {
  const client = useQueryClient();
  const navigate = useNavigate();
  const [query, setQuery] = useState("");

  async function logout() {
    await api("auth/logout", "POST");
    client.clear();
    navigate("/login");
  }

  const tab = ({ isActive }: { isActive: boolean }) =>
    isActive ? "text-white" : "text-dusk-200 hover:text-white";
  return (
    <header className="no-print bg-dusk-900 text-white">
      <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-x-5 gap-y-2 px-4 py-3">
        <Link to="/" className="font-display text-xl">
          Twilight Hearth
        </Link>
        <form
          className="min-w-40 flex-1"
          role="search"
          onSubmit={(event) => {
            event.preventDefault();
            navigate(`/?q=${encodeURIComponent(query)}`);
          }}
        >
          <input
            className="w-full rounded-lg bg-dusk-700 px-3 py-1.5 placeholder:text-dusk-200"
            type="search"
            aria-label="Search recipes"
            placeholder="Search recipes or ingredients"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </form>
        <nav className="flex flex-wrap items-center gap-4 text-sm">
          <NavLink to={`/cook/${me.id}`} className={tab}>My recipes</NavLink>
          <NavLink to="/saved" className={tab}>Saved</NavLink>
          {me.is_admin && <NavLink to="/admin" className={tab}>Admin</NavLink>}
          <button className="text-dusk-200 hover:text-white" onClick={logout}>Sign out</button>
          <Link to="/new" className="rounded-lg bg-ember-600 px-3 py-1.5 font-medium hover:bg-ember-500">
            New recipe
          </Link>
        </nav>
      </div>
    </header>
  );
}

function Profile() {
  const { id } = useParams();
  const user = useApi<User>(`users/${id}`);
  if (user.error) return <Problem error={user.error} />;
  if (!user.data) return null;
  return <Browse key={id} title={`${user.data.display_name}’s recipes`} filter={`owner=${id}`} />;
}
