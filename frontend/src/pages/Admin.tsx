import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, useApi, type AdminUser, type Invite, type InviteCreated, type Me } from "../api";
import { Problem } from "../components";

function status(invite: Invite) {
  if (invite.used_by_id) return "Used";
  if (invite.revoked_at) return "Revoked";
  if (new Date(invite.expires_at) < new Date()) return "Expired";
  return "Open";
}

export function AdminPage({ me }: { me: Me }) {
  const client = useQueryClient();
  const invites = useApi<Invite[]>("admin/invites");
  const users = useApi<AdminUser[]>("admin/users");
  const [email, setEmail] = useState("");
  const [url, setUrl] = useState("");
  const [error, setError] = useState<unknown>(null);

  async function run(work: () => Promise<unknown>) {
    try {
      setError(null);
      await work();
      await client.invalidateQueries();
    } catch (problem) {
      setError(problem);
    }
  }

  function invite(event: React.FormEvent) {
    event.preventDefault();
    void run(async () => {
      const made = await api<InviteCreated>("admin/invites", "POST", { email: email || null });
      setUrl(made.url);
      setEmail("");
    });
  }

  return (
    <div className="space-y-8">
      <Problem error={error ?? invites.error ?? users.error} />
      <section>
        <h1 className="text-3xl">Invites</h1>
        <form onSubmit={invite} className="mt-3 flex flex-wrap gap-2">
          <input className="field max-w-xs" type="email" aria-label="Email" placeholder="Google email (optional)" value={email} onChange={(e) => setEmail(e.target.value)} />
          <button className="btn-primary">Create invite</button>
        </form>
        {url && (
          <div className="card mt-3 p-3">
            <p className="text-sm">Copy this link now. It works once and will not be shown again.</p>
            <input className="field mt-1" aria-label="Invite link" readOnly value={url} onFocus={(e) => e.target.select()} />
          </div>
        )}
        <ul className="mt-3 space-y-1">
          {invites.data?.map((item) => (
            <li key={item.id}>
              {item.email ?? "Anyone with the link"} · {status(item)}
              {status(item) === "Open" && (
                <> · <button className="link" onClick={() => run(() => api(`admin/invites/${item.id}`, "DELETE"))}>Revoke</button></>
              )}
            </li>
          ))}
        </ul>
      </section>
      <section>
        <h2 className="text-2xl">Members</h2>
        <ul className="mt-3 space-y-1">
          {users.data?.map((user) => (
            <li key={user.id}>
              {user.display_name} ({user.email}){user.is_admin ? " · Admin" : ""}{user.disabled_at ? " · Disabled" : ""}
              {user.id !== me.id && (
                <> · <button className="link" onClick={() => run(() => api(`admin/users/${user.id}/${user.disabled_at ? "enable" : "disable"}`, "POST"))}>{user.disabled_at ? "Enable" : "Disable"}</button></>
              )}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
