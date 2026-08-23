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

The tables themselves are created automatically the first time the backend starts, by
`Base.metadata.create_all` in `backend/app/main.py`.

> `CREATE DATABASE` cannot run inside a transaction block. Pasting it in a batch with
> other statements gives you `SQLSTATE 25001` — run it on its own.

### Migrations

`create_all` only creates tables that do not exist yet — it never alters one. Anything that
changes an existing table therefore ships as a numbered file in `migrations/`, applied by
hand, in order:

```bash
psql "$DATABASE_URL" -f migrations/001_add_media_metadata_columns.sql
psql "$DATABASE_URL" -f migrations/002_add_media_catalogue_and_posters.sql
psql "$DATABASE_URL" -f migrations/003_add_media_scores_and_embeddings.sql
```

Each is re-runnable and non-destructive, and each carries a commented-out `DOWN` block at
the bottom.

On a **brand-new** database, `create_all` builds the tables from `models.py` — including
their `CHECK` constraints and indexes — so the column-adding parts of each migration find
nothing to do. Run them anyway: `002` also creates the `media_primary_poster` view and the
backfills that move existing data into the new shape, and neither of those is expressible
as a model definition.

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

`TMDB_API_KEY` and `GEMINI_API_KEY` are both optional — see `.env.example`. Without them
the app runs normally; you lose posters and suggestions without the first, and the
assistant without the second. Both are free to obtain.

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

## Ask your watchlist

A floating widget in the bottom-right corner of the dashboard answers questions about your
items — factual (*"what did I rate 5 stars?"*), open-ended (*"something slow I haven't
started"*), and about films you don't track at all (*"what is The Matrix about?"*).

**Retrieval runs locally and finishes before Gemini is contacted**, so a question costs
exactly one API request. The prompt carries two blocks, and the split is the whole design:

| Block | Contents | Why |
| --- | --- | --- |
| `INDEX` | Every title, one line — status, your rating, TMDB score, platform, genres | Factual questions have to be *exact*, and exactness needs the complete list. One line each is cheap enough to always send |
| `DETAIL` | Full synopses for the ~8 titles most related to *this* question | Mood questions need prose to work, but never need all of it |
| `NOT ON THE WATCHLIST` | A live TMDB record, when the question names a film you don't track | Lets it answer about anything without inventing it — the facts come from TMDB, not from model recall |
| `TMDB SEARCH RESULTS` | Credits and matching titles, when the question asks for a *list* involving a person or character | *"What films have Batman in them?"*, *"what did Nolan direct?"* — answers that span all of TMDB, not just your list |

`DETAIL` is chosen two ways at once, because they fail in opposite directions: similarity
search over `media.embedding` (finds *"slow and melancholy"* in a synopsis using neither
word, but can rank a directly-named title low) and a word-boundary name match (exact, but
blind to anything phrased by theme).

This keeps the prompt roughly flat as a watchlist grows — the index scales linearly but
stays small, and the expensive half is capped.

Two different extractors decide what gets looked up, because the two question shapes need
opposite biases:

- **One title** (*"what is The Matrix about?"*) — `assistant._extract_titles` keys on
  quoting and capitalisation. All-lowercase *"what is the matrix about?"* therefore finds
  nothing and the model answers from general knowledge instead, saying so. A deliberate
  bias: a false positive costs a wasted TMDB call and irrelevant facts in the prompt, while
  a false negative still gives a usable answer.
- **A list** (*"what films have batman in them?"*) — `_LISTING_INTENT` recognises the
  phrasing first, and only then does `_listing_subject` take whatever survives removing the
  question vocabulary. Capitalisation can't be the signal here, because people type
  character names in lower case. Both a person lookup and a title search run, since the
  question rarely says which it meant; they fail cleanly in opposite directions, so
  whichever is wrong returns nothing.

The noise list that `_listing_subject` strips includes watchlist vocabulary (*finished*,
*dropped*, *own*) and genres. Without it, *"what films have I finished?"* reads as a list
request and sends TMDB a search for `"finished"`.

Anything about *you* — your rating, your status — is answered only from `INDEX`, never
guessed, whichever blocks are present.

`tmdb.search_person` filters out appearances-as-themselves. Talk shows dominate a working
actor's credits by popularity, so without that filter *"what is Cillian Murphy in?"* leads
with three chat shows before any film.

It also verifies that the person TMDB returned is plausibly the one asked for, by requiring
every searched word to appear in the returned name. TMDB matches nicknames, so a search for
the *character* `Iron Man` comes back with **Mike Tyson** — "Iron Mike" — at high
popularity. That is worse than an empty result, because a person match suppresses the title
search that would have found the actual films. Surname-only searches still work: `Nolan`
resolves to Christopher Nolan.

> **Misspelled names cannot be looked up.** TMDB matches names exactly — `Denis Vilneurve`
> returns nothing, and `Spielburg` returns a *different, real* person ("Yung Spielburg"),
> which is worse. There is no fuzzy mode to switch on. So the assistant is told to answer
> from general knowledge when a lookup finds nothing, flag that it is doing so, and suggest
> the spelling it thinks was meant — asking again with the correct spelling gets grounded
> TMDB data. Answering *"no films by X are on your watchlist"* is explicitly ruled out,
> since it answers a question nobody asked.

> **Character searches are inherently partial.** They match titles by name, so *"where does
> Iron Man appear?"* finds the Iron Man films but not *Spider-Man: Homecoming* — TMDB has no
> global character index to query. The prompt therefore tells the model to list the search
> results in full and then add well-known missing appearances from its own knowledge, in a
> separate sentence, marked as such. It is likewise told never to silently drop an entry it
> does not recognise or that has not been released yet: an unreleased title is exactly what
> the user cannot supply from memory, and it is in the block because it is real.

> An earlier version instead gave the model three tools and let it choose, which was
> elegant but cost a network round trip per decision — about three requests per question
> against a free-tier allowance of five per minute. Doing the retrieval locally is not a
> workaround for that limit; it is less work for the same answer, and at this corpus size
> it produces *better* answers, because the model sees the whole list rather than whatever
> two tool calls happened to return.

**Setup.** Two independent pieces, and neither costs anything:

- `GEMINI_API_KEY` in `backend/.env` powers the answers. Get one free, with no card, at
  [aistudio.google.com/apikey](https://aistudio.google.com/apikey). Without it the panel
  says it is not configured and everything else keeps working.
- The similarity search needs **no key at all** — it runs a small model locally,
  downloaded once (~67 MB) on first use and offline thereafter.

### Rate limits

The free tier allows a few requests per minute, **counted per model**. An exhausted quota
says so explicitly:

```
limit: 5, model: gemini-3.7-flash
quotaDimensions: {model: gemini-3.7-flash, location: global}
```

Two things keep you clear of it. One question is one request (above), and a `429` falls
through to the next model in `assistant.MODELS`, each of which has its own allowance.
Measured: five varied questions asked back-to-back all succeeded, in 27 seconds.

The chain advances on `429` **only**. A bad key or a missing model would fail identically
on every entry, so those raise immediately rather than retrying twice more to reach the
same conclusion slower. `assistant._explain` then maps each failure to one actionable line,
so the panel tells you whether to *wait* (`429`, `503`) or to *fix something* (`404`,
`401`) instead of printing a JSON blob.

`GEMINI_MODEL` pins a single model and disables the fallback. Unset, the chain starts at
the `gemini-flash-latest` alias rather than a pinned version on purpose: specific names get
retired, and `gemini-2.5-flash` — the first default written here — already returns 404 for
new keys. Note that `models.list()` still advertises retired models, so the only way to
know a name works is to call it.

Only `app/assistant.py` is tied to Gemini. The retrieval half — `app/embeddings.py`, the
embedding columns, `backfill_media.py` — is provider-independent, so swapping the answering
model later means rewriting one file.

After running migration `003`, fill in the new columns for titles you already track:

```powershell
cd backend
.\.venv\Scripts\python.exe backfill_media.py --dry-run   # see what it would do
.\.venv\Scripts\python.exe backfill_media.py
```

It has two passes — TMDB scores (needs `TMDB_API_KEY`) and embeddings (local) — either
skippable with `--skip-scores` / `--skip-embeddings`. Re-running it is safe: each pass only
selects rows still missing its column.

> **On the similarity threshold.** `embeddings.MIN_SCORE` rejects unrelated matches, and
> its value is *measured, not guessed* — the comment above it records what the scores
> actually look like on real data and why two earlier, more intuitive values silently threw
> away correct answers. Re-measure it if you change the model.

### Am I running the code I just edited?

Uvicorn serves whatever it loaded at startup. Edit a file without `--reload` and the
running server keeps answering from the old code — and because the symptom is a *stale
answer* rather than an error, it is indistinguishable from a bug in the new code. On
Windows this bites harder than it should: closing the terminal does not reliably kill the
process, so an orphan can hold port 8000 while you think you restarted.

`GET /` reports the newest source file the running process loaded:

```bash
curl -s http://127.0.0.1:8000/
# {"message":"...","code_loaded_at":"2026-08-23T10:41:34+00:00"}
```

If that timestamp is older than your last edit, the server is stale. Restart it — and
prefer `--reload` during development:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

If a restart does not change the timestamp, an orphaned process still owns the port:

```powershell
Get-NetTCPConnection -LocalPort 8000 -State Listen | ForEach-Object { Get-Process -Id $_.OwningProcess }
```

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
| `POST` | `/assistant/ask` | Ask a question about your watchlist |

Every watchlist and dashboard route filters by the token's user, so one account cannot
read or modify another's items.

## Project layout

```
backend/
  app/
    main.py          app setup, CORS, table creation
    database.py      engine and session
    models.py        User, WatchlistItem, Media, MediaPoster
    schemas.py       Pydantic models and validation
    dependencies.py  token creation, get_current_user
    tmdb.py          TMDB client, shared with the MCP server
    media_catalogue.py  resolves items to the shared catalogue
    embeddings.py    semantic search — the one place similarity lives
    assistant.py     the assistant's tools and Claude loop
    routers/         auth, watchlist, dashboard, media, assistant
  backfill_posters.py  posters for items added before enrichment existed
  backfill_media.py    scores and embeddings for rows predating 003
migrations/          numbered SQL, applied by hand, in order
frontend/
  src/
    api.js           fetch wrapper, token storage, error normalisation
    constants.js     status order, labels, colours
    App.jsx          signed-in vs signed-out
    components/      Login, Dashboard, StatsBar, AddItemForm, ItemCard,
                     StarRating, AssistantPanel
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
