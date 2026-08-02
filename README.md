# Media Watchlist

Track what you plan to watch, what you're watching, what you finished (and how you rated
it), and what you dropped.

FastAPI + PostgreSQL on the back end, React + Vite + Tailwind CSS v4 on the front end.

## Prerequisites

- **Python 3.11+**
- **Node.js 18+**
- **PostgreSQL 14+** running locally

## 1. Create the database

Connect to PostgreSQL — pgAdmin's Query Tool, or `psql -U postgres` — and run:

```sql
CREATE DATABASE media_watchlist;
```

That is the only schema step. The tables are created automatically the first time the
backend starts, by `Base.metadata.create_all` in `backend/app/main.py`.

> `CREATE DATABASE` cannot run inside a transaction block. Pasting it in a batch with
> other statements gives you `SQLSTATE 25001` — run it on its own.

## 2. Back end

From the repo root:

```bash
cd backend
python -m venv .venv
```

Install dependencies — **Windows (PowerShell)**:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

**macOS / Linux**:

```bash
./.venv/bin/pip install -r requirements.txt
```

Create your environment file from the template:

```powershell
copy .env.example .env    # Windows
```

```bash
cp .env.example .env      # macOS / Linux
```

`backend/.env` needs two values:

```
DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@localhost:5432/media_watchlist
SECRET_KEY=<a long random string>
```

Generate the secret rather than inventing one:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

**Do not skip `SECRET_KEY`.** [`dependencies.py:9`](backend/app/dependencies.py#L9) falls
back to a hard-coded default when the variable is missing, so the app starts up perfectly
happily and signs every token with a value that is public in this repository.

Start the API, from `backend/`:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

```bash
./.venv/bin/python -m uvicorn app.main:app --reload
```

It serves on <http://127.0.0.1:8000>. Interactive API docs: <http://127.0.0.1:8000/docs>.

## 3. Front end

In a second terminal, from the repo root:

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>.

**The front end must run on port 5173.**
[`main.py:12`](backend/app/main.py#L12) allows exactly that one CORS origin, so on any
other port every request fails in the browser. `vite.config.js` sets `strictPort: true`
deliberately — if 5173 is occupied, Vite errors out instead of quietly moving to 5174 and
leaving you with a UI that loads but cannot reach the API.

## How it works

Sign in with an email address. `POST /auth/register` creates the account and
`POST /auth/login` returns a token for an existing one; the token is kept in
`localStorage` and sent as `Authorization: Bearer <token>`.

**There are no passwords** — anyone who knows an email address can sign in as that user.
This is a deliberate scope cut, not an oversight. See [Known limitations](#known-limitations).

Each item has a title, a platform, and one of four statuses:

| Status | Meaning |
| --- | --- |
| `planning_to_watch` | On the list, not started |
| `watching` | In progress |
| `finished` | Done — **requires a 1–5 rating** |
| `dropped` | Abandoned |

The rating rule is enforced on both sides. Moving an item to *Finished* without a rating
returns 422, so the UI collects the stars first and sends status and rating together.
Moving an item away from *Finished* clears the rating.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/auth/register` | Create an account, returns a token |
| `POST` | `/auth/login` | Token for an existing account |
| `GET` | `/watchlist/` | The current user's items |
| `POST` | `/watchlist/` | Add an item |
| `PATCH` | `/watchlist/{id}` | Update title, platform, status or rating |
| `DELETE` | `/watchlist/{id}` | Remove an item |
| `GET` | `/dashboard/` | Items grouped by status, plus counts |

Every watchlist and dashboard route filters by the token's user, so one account cannot
read or modify another's items.

## Project layout

```
backend/
  app/
    main.py          app setup, CORS, table creation
    database.py      engine and session
    models.py        User, WatchlistItem
    schemas.py       Pydantic models and validation
    dependencies.py  token creation, get_current_user
    routers/         auth, watchlist, dashboard
frontend/
  src/
    api.js           fetch wrapper, token storage, error normalisation
    constants.js     status order, labels, colours
    App.jsx          signed-in vs signed-out
    components/      Login, Dashboard, StatsBar, AddItemForm, ItemCard, StarRating
```

## Developing

Front-end checks, from `frontend/`:

```bash
npm run lint     # oxlint
npm run build    # production build
```

Tailwind is **v4**, configured through the `@tailwindcss/vite` plugin and a single
`@import "tailwindcss"` in `src/index.css`. There is no `tailwind.config.js` and no
PostCSS config, and adding one is not needed — that is the v3 arrangement.

Class names must be written out in full. `` className={`bg-${colour}-400`} `` generates
no CSS, because Tailwind scans source text and only sees complete literal strings.

If you use Claude Code, `/new-UI-component` scaffolds a component in the conventions
above — see `.claude/commands/new-UI-component.md`.

## Known limitations

Deliberate scope cuts, listed so they are not mistaken for bugs:

- No passwords — an email address alone is enough to sign in.
- Tokens carry no `exp` claim, so they never expire.
- `status` is validated by Pydantic but has no database `CHECK` constraint. A row written
  outside the API with an unrecognised status would break `GET /dashboard/`.
- No automated test suite in the repository.
