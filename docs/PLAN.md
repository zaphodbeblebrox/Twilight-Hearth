# Twilight Hearth: Plan

An invite-only recipe app for friends and family, modeled on GitHub: import recipes
from anywhere, fork them, and see how they change over time.

Hosted on `twilight` at twilight-hearth.net.

## Decisions

| Topic | Decision | Status |
|---|---|---|
| Frontend | React, TypeScript, Tailwind | Decided |
| Backend | Python | Decided |
| Audience | Invite-only, friends and family | Decided |
| Meal planning, shopping lists | Future; not in phases 1-4 | Decided |
| Python framework | FastAPI | Decided |
| Login | Google account only; no passwords | Decided |
| Visibility | Visible to all members by default; optional private | Decided |
| Community groups | Future: members form groups with selected users | Decided |
| Photo import | Hosted vision model, with spending cap | Decided |
| Vision model | Claude Haiku 5.5, retry with Sonnet 5.5; confirm by testing | Proposed |

## Stack

- **Frontend:** Vite, React Router, TanStack Query. API client generated from OpenAPI.
- **Backend:** FastAPI, Pydantic, SQLAlchemy 2, Alembic, managed with `uv`.
- **Database:** PostgreSQL 18 (already on twilight), dedicated database and user.
- **Login:** Google OpenID Connect, using Authlib.
- **Jobs:** Procrastinate, a Postgres-backed queue (no Redis).
- **Import:** `recipe-scrapers`, `ingredient-parser`, hosted vision model.

Why FastAPI: one Pydantic `RecipeContent` model can validate scraper output, model
output, API requests, and stored revisions, and generate the frontend types. Google
handles credentials, leaving invites and sessions to build.

## Layout

    backend/    FastAPI app, job worker, migrations, tests
    frontend/   Vite + React app
    deploy/     systemd units, nginx config, backup script
    docs/

## Data model

| Table | Key fields |
|---|---|
| `user` | google_sub (unique), email, display_name, is_admin, disabled_at |
| `invite` | token_hash, email (optional), created_by, expires_at, used_by |
| `session` | token_hash, user_id, expires_at |
| `recipe` | owner_id, visibility, current_number, forked_from_id, search copies of content, deleted_at |
| `revision` | recipe_id, number, parent_id, author_id, message, content (JSONB), created_at |
| `favorite`, `rating`, `comment` | user and recipe, plus stars or text |
| `import_job` (phase 2) | user_id, source_type, source_ref, status, draft (JSONB), error, cost |
| `image` | owner_id; file named by id |

Rules:

1. Revisions are never edited. Every save adds one; restoring adds a copy of an old one.
2. Forking creates a new recipe whose first revision has the source revision as its
   parent. `parent_id` can therefore cross recipes, giving one ancestry graph.
3. Saving requires the revision the edit started from. A stale base returns 409.
4. Deletes are soft, so forks keep their lineage. Forks of hidden or deleted sources
   show attribution but not the source's content.
5. Only recipes the user can view can be forked.

### Login and invites

Google proves who someone is; an invite decides whether they may join.

1. An invite link is opened and held in a signed, HttpOnly cookie while the user signs in with Google.
2. The server runs the authorization code flow with PKCE, state, and nonce, and
   validates the ID token (signature, issuer, audience, expiry, nonce).
3. Known `google_sub`: sign in. Unknown: require a valid invite, consume it, and create
   the user in one transaction. Otherwise refuse.

- Identity is `google_sub`, never email, since an email can change.
- If the invite names an email, the Google email must match and be verified.
- Scopes are only `openid email profile`. Google tokens are not kept after login.
- A command on the server creates the first admin's invite.
- Disabling a user revokes their sessions immediately.
- Development and automated tests use a fake provider that cannot be enabled in
  production.

### Recipe content (stored in each revision)

- title, description, yield, prep and cook times, tags, image ids
- source: URL, book, or person, plus the original author
- ingredient groups, each with ingredients:
  stable id, original text, quantity (exact decimal/fraction, optional max), unit, food, note
- steps: stable id, text, optional ingredient ids
- notes, `schema_version`

Stable ids let a diff tell "changed" from "removed and added". Original text is always
kept because parsing is imperfect.

### Leaving room for meal planning and shopping lists

Structured quantity/unit/food is what shopping lists will need to combine items. A
future `meal_plan_entry` can reference a recipe and optionally pin a revision. Nothing
else is needed now.

### Leaving room for community groups

Later tables: `group`, `group_member` (with role), `recipe_group` (a recipe can be in
several groups). `visibility` gains a `group` value. To make that cheap:

- All reads go through one `can_view` / `visible_to(user)` rule from phase 1, including
  search, images, revision history, diffs, and fork trees.
- A fork of a group recipe defaults to the same group, and widening its audience warns
  the user, so forking does not quietly publish a restricted recipe. Likewise a fork of
  a private recipe starts private.
- Open: what happens to a member's forks and access when they leave a group.

## Import pipeline

    source -> extract -> normalize -> user review -> revision 1

| Source | Extraction |
|---|---|
| URL | recipe-scrapers; fall back to model on page text |
| JSON / text file | direct parse (schema.org, Cooklang) or model |
| PDF | text layer; fall back to vision |
| Photo | vision model |

Extraction runs as a job. Nothing is published without user review.

The model sits behind one `extract()` interface so it can be swapped. Starting limits:
20 model imports per user per day, $10 per month for the app, and prepaid provider
credit without auto-reload. Model names and prices are configuration, not code.

## Hosting

    Cloudflare Tunnel -> nginx -> frontend static files
                              \-> /api -> FastAPI (localhost) -> Postgres

- systemd services for API and worker, running as a dedicated user
- Ports 8000 and 8080 are in use on twilight; use 8100 if free
- Node is only needed to build, not to run
- Nightly `pg_dump` plus images, copied off the server, with a tested restore

## Security

- Invite tokens: single-use, expiring, stored hashed
- No passwords stored. Google client secret lives only in a root-readable env file
- Sessions: HttpOnly, Secure, SameSite=Lax cookies; CSRF protection; server-side revocation
- Rate limits on login, invite redemption, and imports
- URL import: http(s) only, block non-public addresses at connection time and on each
  redirect, limit size and time
- Uploads: size limits, re-encode images, strip metadata, check access when serving
- Extracted text is untrusted: validate against schema, never render as raw HTML
- Per-user import limits and a monthly spending cap

## Phases

1. **Core:** invites and Google login; recipe create, edit, view; revision history and
   restore; photos, search, tags, scaling, printing; saved recipes, ratings, comments;
   fork with credit and comparison. Built. Remaining: deployment and backups
2. **Import:** URL, then file, then photo
3. **Fork extras:** visual family tree, "original has changed" notices
4. **Social:** "I made this", suggested changes, collections
5. **Future:** community groups, meal planning, shopping lists

Phase 1 is done when an invited user can join with Google at twilight-hearth.net, an
uninvited Google account is refused, and a user can create a recipe, edit it twice, restore the first version, and a backup has been restored
successfully.
