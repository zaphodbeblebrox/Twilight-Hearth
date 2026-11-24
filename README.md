# Twilight Hearth

Friends and family recipe sharing app: share recipes, fork each other's, and see how
they change over time. The design is in [docs/PLAN.md](docs/PLAN.md).

## Develop

Needs [uv](https://docs.astral.sh/uv/) and [Node.js](https://nodejs.org/) 24 or newer.
Postgres for development is downloaded with the Python packages.

Backend, in `backend/`:

    cp .env.example .env
    uv run alembic upgrade head
    uv run python -m app.cli invite --admin    # prints your invite link
    uv run uvicorn app.main:app --port 8100 --reload

Frontend, in `frontend/`:

    npm ci
    npm run dev

Open the invite link and use the development login. It follows the same invite rules
as Google and does not exist when `TH_ENV=production` (the default).

## Check

    cd backend && uv run pytest && uv run ruff check .
    cd frontend && npm run build

After changing the API:

    cd backend && uv run python -m app.cli openapi ../frontend/openapi.json
    cd ../frontend && npm run gen:api
