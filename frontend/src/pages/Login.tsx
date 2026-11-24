import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router";
import { api, useApi, type AuthConfig } from "../api";
import { Problem } from "../components";

const MESSAGES: Record<string, string> = {
  invite_required: "That account is not a member yet. Ask for an invite link.",
  invite_invalid: "That invite has expired or was already used. Ask for a new one.",
  invite_email_mismatch: "That invite is for a different email address.",
  account_disabled: "That account has been disabled.",
  google_failed: "Google sign-in did not finish. Please try again.",
};

function SignIn({ heading, code }: { heading: string; code?: string | null }) {
  const config = useApi<AuthConfig>("auth/config");
  const [name, setName] = useState("");
  const [error, setError] = useState(code);

  async function devLogin(event: React.FormEvent) {
    event.preventDefault();
    try {
      const email = `${name.trim().toLowerCase().replace(/\s+/g, ".")}@example.com`;
      await api("auth/dev-login", "POST", { name, email });
      window.location.assign("/");
    } catch (problem) {
      setError((problem as Error).message);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-dusk-900 p-4">
      <div className="card w-full max-w-sm p-8 text-center">
        <h1 className="text-3xl">Twilight Hearth</h1>
        <p className="mt-2 text-dusk-500">{heading}</p>
        {error && <Problem error={new Error(MESSAGES[error] ?? error)} />}
        {config.data?.google && (
          <a href="/api/auth/google/login" className="btn mt-6 block py-2.5">Sign in with Google</a>
        )}
        {config.data?.dev_login && (
          <form onSubmit={devLogin} className="mt-6 border-t border-dusk-200 pt-4 text-left">
            <label className="label" htmlFor="dev-name">Development login</label>
            <div className="flex gap-2">
              <input id="dev-name" className="field" placeholder="Any name" required value={name} onChange={(e) => setName(e.target.value)} />
              <button className="btn">Go</button>
            </div>
          </form>
        )}
        <p className="mt-6 text-sm">
          <a className="link" href="/about.html">About</a> · <a className="link" href="/privacy.html">Privacy</a> ·{" "}
          <a className="link" href="/terms.html">Terms</a>
        </p>
      </div>
    </main>
  );
}

export function Login() {
  const [params] = useSearchParams();
  return <SignIn heading="Family recipes, shared and remixed" code={params.get("error")} />;
}

export function Join() {
  const [token] = useState(() => window.location.hash.slice(1));
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<unknown>(token ? null : new Error("This invite link is incomplete."));
  const sent = useRef(false);

  useEffect(() => {
    if (!token || sent.current) return;
    sent.current = true;
    api("auth/invite", "POST", { token }).then(
      () => {
        window.history.replaceState(null, "", "/join");
        setReady(true);
      },
      setError,
    );
  }, [token]);

  if (ready) return <SignIn heading="You’re invited! Sign in to join." />;
  return <main className="mx-auto max-w-sm p-8"><Problem error={error} /></main>;
}
