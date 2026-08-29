# n8n automation

Workflows that run *beside* the app, never inside it.

Nothing in this directory is imported by the API, the frontend, or the MCP server. Deleting
it changes no application behaviour — it is here so the automation is version-controlled
next to the schema it reads.

## `stale-watching-nudge.json`

Emails each user a weekly list of titles they left in `watching` and never finished. The
dashboard shows a count but not an age, so a title parked for two months looks identical to
one started yesterday; this closes that gap.

**Read-only.** The workflow issues one `SELECT`. It cannot write, and if n8n is stopped,
broken, or deleted, the app is unaffected — the emails simply stop.

### Setup

1. **Run n8n** (free forever self-hosted; the 14-day trial applies only to n8n Cloud):

   ```
   docker run -d --name n8n -p 5678:5678 \
     -e N8N_ENCRYPTION_KEY=<any long random string> \
     -e GENERIC_TIMEZONE=Europe/Sarajevo \
     -v n8n_data:/home/node/.n8n docker.n8n.io/n8nio/n8n
   ```

   Open <http://localhost:5678>. Once the app is deployed, run n8n as a second service on
   the same Docker network instead, and reach Postgres by service name.

2. **Import**: Workflows → ⋯ → *Import from File* → `stale-watching-nudge.json`.

3. **Postgres credential** on the `Find stale` node.
   - Host: `host.docker.internal` (n8n in Docker, database on this machine), or the
     Postgres service name once both are deployed together
   - Port `5432`, database `media_watchlist`

   Optional hardening — give n8n its own read-only login instead of the app's account:

   ```sql
   CREATE ROLE n8n_ro LOGIN PASSWORD '<strong password>';
   GRANT CONNECT ON DATABASE media_watchlist TO n8n_ro;
   GRANT USAGE ON SCHEMA public TO n8n_ro;
   GRANT SELECT ON users, watchlist, media, media_posters, media_primary_poster TO n8n_ro;
   ```

   Additive: it creates a role and grants reads, altering no table and no app behaviour.

4. **Email credential** on the `Send nudge` node, and set `fromEmail` (currently
   `CHANGE_ME@your-domain`). The node is SMTP — host, port, app password. Swap it for the
   Gmail node only if the *sending* account is Google. **Recipients can be on any provider**;
   that is independent of which node sends.

### Before enabling the schedule

This database contains seed and QA accounts, three of which have `watching` items. The query
therefore excludes `%@example.com` and `%.local`, because those addresses hard-bounce and
repeated bounces get SMTP senders throttled. **Remove those two lines once the test users are
cleaned up** — until then they are the only thing stopping a weekly send to fake addresses.

### Tuning

- **Threshold**: `interval '14 days'` in the SQL.
- **Cadence**: the Schedule Trigger node. Weekly is deliberate — a daily nudge about a film
  you are halfway through becomes noise you learn to ignore.
- **Poster size**: `media_primary_poster` ignores size, so the URL may be the multi-megabyte
  `original`. For a smaller image, join `media_posters` with `size_label = 'w500'` instead.

### Verify without waiting two weeks

Run these against the database directly; each answers one question.

| Check | How |
| --- | --- |
| Query is valid and scoped right | `psql "$DATABASE_URL" -f` the SQL from the node |
| Multi-user works | Confirm rows for more than one `email` |
| Threshold works | Change to `interval '0 days'` — every `watching` item appears |
| Nobody gets an empty email | Change to `interval '99999 days'` — 0 rows, workflow ends at the Code node |
| App is unaffected | Stop the n8n container, then add/rate/delete an item in the app |
