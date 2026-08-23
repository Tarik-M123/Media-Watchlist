"""The "ask your watchlist" assistant.

Retrieval runs locally and finishes before Gemini is contacted, so answering a
question costs exactly one API request. The earlier version handed Gemini three
tools and let it decide which to call, which was elegant but cost a round trip
per decision — three requests against a free-tier allowance of five per minute,
i.e. under two questions a minute. Doing the retrieval ourselves is not a
workaround for that limit; it is simply less work for the same answer.

The context handed over has two parts, and the split is the whole design:

  * An INDEX of every item, one line each. Factual questions ("what did I rate
    5?") have to be exact, and exactness needs the complete list. One line per
    title is cheap enough to always send.
  * DETAIL — full synopses — for only the handful of titles relevant to this
    particular question, chosen by embedding similarity. Mood questions ("slow
    and melancholy") need prose to work, but they never need all of it.

That keeps the prompt roughly flat as a watchlist grows: the index scales
linearly but stays tiny, and the expensive half is capped.

Only this module is provider-specific. The retrieval half — embeddings.py, the
embedding columns, backfill_media.py — needs no API key and is untouched by
which model answers.
"""

import logging
import os
import re

from google import genai
from google.genai import types
from sqlalchemy.orm import Session

from app import embeddings, models, tmdb

logger = logging.getLogger(__name__)

# Tried in order, and only ever advanced past on a 429. The free-tier quota is
# dimensioned per model — an exhausted request reports
# `quotaDimensions: {model: gemini-3.7-flash}` — so a second model is a second
# allowance rather than the same one under a different name.
#
# The first entry is an alias on purpose: specific names get retired, and
# gemini-2.5-flash (the original default here) already 404s for new keys.
DEFAULT_MODELS = ("gemini-flash-latest", "gemini-3.5-flash", "gemini-3.1-flash-lite")

_configured = (os.getenv("GEMINI_MODEL") or "").strip()
MODELS = (_configured,) if _configured else DEFAULT_MODELS

MAX_OUTPUT_TOKENS = 2048

# How many titles get their synopsis included. Comfortably more than any one
# question needs, while keeping the prompt bounded on a large watchlist.
DETAIL_LIMIT = 8

# Ceiling on index lines. Far above any realistic personal watchlist; it exists
# so a runaway account cannot build a multi-megabyte prompt.
INDEX_LIMIT = 400

# Short titles ("Up", "It") appear inside ordinary words, so matching them
# against free text produces nonsense. Below this length, only exact-ish
# word-boundary matches count.
MIN_TITLE_MATCH = 3

# How many off-watchlist titles to look up on TMDB per question. Each costs a
# search plus a details call, so this is kept low deliberately.
EXTERNAL_LIMIT = 2

# Words that are never part of a title, used to trim candidates extracted from a
# question. Without this, "Is Inception any good?" yields "Is Inception".
_QUESTION_WORDS = {
    "what", "whats", "who", "when", "where", "why", "how", "do", "does", "did",
    "is", "are", "was", "were", "can", "could", "should", "would", "i", "my",
    "me", "have", "has", "had", "the", "a", "an", "of", "or", "any", "about",
    "tell", "show", "give", "find", "watch", "watched", "watching", "seen",
    "see", "long", "good", "bad", "like", "list", "on", "in", "to", "and", "it",
    "that", "this", "there", "yet", "still", "recommend", "rate", "rated",
    "rating", "score", "scored", "movie", "film", "series", "stars", "star",
}

# Questions that want a LIST of titles involving someone or something, rather
# than facts about one title. "What films is Cillian Murphy in?" is this;
# "Is Inception any good?" is not.
_LISTING_INTENT = re.compile(
    r"\b(?:what|which|any|all|list|show\s+me)\b[^?]*\b(?:films?|movies?|shows?|series|titles?)\b"
    r"|\b(?:films?|movies?|shows?|series|titles?)\b[^?]*"
    r"\b(?:with|in|by|from|featuring|starring|directed|played|plays)\b"
    r"|\b(?:filmography|directed\s+by|starred\s+in|acted\s+in|appears?\s+in)\b",
    re.I,
)

# Stripped out when isolating the subject of a listing question. Genres are
# included because "what sci-fi films do I have?" is a watchlist question, and
# searching TMDB for "sci-fi" would return noise nobody asked for.
_LISTING_NOISE = _QUESTION_WORDS | {
    "films", "movies", "shows", "series", "titles", "them", "they", "he", "she",
    "his", "her", "their", "from", "featuring", "starring", "starred", "direct",
    "directed", "directs", "director", "acted", "acts", "appear", "appears",
    "appeared", "played", "plays", "played", "cast", "filmography", "all",
    "which", "some", "many", "much", "been", "was", "were", "with", "for",
    "scifi", "sci-fi", "comedy", "comedies", "drama", "dramas", "horror",
    "thriller", "thrillers", "action", "romance", "romantic", "documentary",
    "documentaries", "animation", "animated", "fantasy", "mystery", "mysteries",
    # Watchlist vocabulary. "What films have I finished?" reads as a listing
    # question to the pattern above, and without these the subject comes out as
    # "finished" and TMDB gets searched for it.
    "finished", "unfinished", "dropped", "planning", "planned", "started",
    "own", "owned", "mine", "watchlist", "queue", "left", "remaining",
    # Filler that otherwise survives as a one-word "subject" — "what films am I
    # still watching?" was yielding "am".
    "am", "be", "being", "still", "currently", "now", "already", "ever",
    "just", "also", "im", "ive", "get", "got",
    # People name the kind of thing they are asking about, and it is not part of
    # the name: "where does the character Iron Man appear?" was searching TMDB
    # for the literal string "character Iron Man" and finding nothing. Common
    # misspellings are listed because this word is one of the most misspelled in
    # English and a typo here silently costs the whole lookup.
    "character", "characters", "charachter", "charachters", "charater",
    "charecter", "charactor", "role", "roles", "actor", "actress", "person",
    "played", "portrayed", "voice", "voiced",
}

_QUOTED = re.compile(r'["“‘\']([^"”’\']{2,60})["”’\']')

# A capitalised run, optionally continued through lowercase connectives.
# The \b after the connective group matters: without it, "about" is consumed as
# the connective "a" and "The Matrix about" extracts as "The Matrix a".
_CAPITALISED_RUN = re.compile(
    r"\b([A-Z][\w'’.-]*(?::)?(?:\s+(?:of|the|and|a|an|in|on|to|vs\.?|part|[A-Z0-9][\w'’.:-]*)\b){0,10})"
)

SYSTEM_PROMPT = """\
You answer questions about the user's personal film and TV watchlist.

The user's message carries a WATCHLIST block with up to three parts:

INDEX lists every title the user tracks, one per line, and is complete — if a
title is absent from INDEX, it is not on their watchlist.

DETAIL adds synopses for the titles most related to the question. It is not
complete; a title missing from DETAIL is still on the watchlist.

NOT ON THE WATCHLIST appears when the question named a film the user does not
track. Those facts come from TMDB and are reliable — use them freely, and say
plainly that the title is not on their watchlist. You may offer to have them add
it, but do not add anything yourself; you cannot change their list.

TMDB SEARCH RESULTS appears when the question asked for a list of titles
involving a person or a character — "what films have Batman in them?", "what did
Nolan direct?".

List everything in that block that fits the question, most notable first. Do not
silently drop an entry because you do not recognise it or because it has not
been released yet — an unfamiliar or upcoming title is exactly what the user
cannot get from memory, and it is in the block because it is real. Only leave
out entries that plainly do not answer what was asked.

The block is a search result, not a complete filmography, so never present it as
exhaustive. It is especially incomplete for characters, because the search
matches titles by name: it finds the films named after a character but not the
other films they turn up in. When you know of well-known appearances that are
missing, add them, in a separate sentence, marked as coming from your own
knowledge rather than the search.

It is also not the user's watchlist, so cross-reference INDEX and mark the ones
they already track rather than implying they own any of it.

Anything about the user — their rating, their status, whether they own or have
seen something — comes only from INDEX. Never guess at it, and never state a
TMDB score that was not given to you; those are facts you either have or do not.

When a film, person, or character is in none of the blocks, still answer. Use
your own knowledge, say up front that you are going from general knowledge
rather than their watchlist, and keep to what is widely known — never invent a
specific score, runtime, or release year that way. If you are unsure something
exists, say so rather than inventing it.

That case is common and is not a dead end: the lookup misses whenever a name is
misspelled, because the search behind these blocks matches names exactly. Never
answer a question about a person or character by talking only about the
watchlist — "no films by X are on your watchlist" answers a question nobody
asked. Say what they wanted to know, and if you think the name was misspelled,
give the spelling you believe was meant so they can ask again for exact data.

Two ratings exist and they are not interchangeable. "your rating" is the user's
own 1-5 score, and "none" means they have not rated it. "TMDB" is the public
0-10 average. If it is ambiguous which was meant, give both when you have them.

Respect the question's constraints exactly. "Something I haven't finished" rules
out anything with status finished, however well it otherwise fits.

Keep answers short — a sentence or two for a lookup, a brief list when asked for
several titles. No preamble, no restating the question, no closing offers of
further help. Give the title and the one detail that answers the question, not
every field you were shown.\
"""


class AssistantUnavailable(RuntimeError):
    """Raised for anything the caller can act on: no API key, no model, no quota."""


def _client() -> genai.Client:
    # The SDK reads GEMINI_API_KEY itself, but checking here turns "no key" into
    # an explanation the panel can show rather than an exception from inside a
    # request.
    key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
    if not key:
        raise AssistantUnavailable(
            "GEMINI_API_KEY is not set, so the assistant is unavailable.\n"
            "  1. Get a free key at https://aistudio.google.com/apikey\n"
            "  2. Add `GEMINI_API_KEY=your_key` to backend/.env\n"
            "  3. Restart the API\n"
            "The rest of the watchlist works normally without it."
        )
    return genai.Client(api_key=key)


def _describe(item: models.WatchlistItem) -> str:
    """One watchlist row as a single index line."""
    media = item.media
    bits = [item.title]
    # Titles are free text, and people habitually type the year into them
    # ("Arrival (2016)"). Appending it unconditionally renders "(2016) · (2016)".
    if item.year and f"({item.year})" not in item.title:
        bits.append(f"({item.year})")
    if item.media_type:
        bits.append(item.media_type)
    bits.append(f"status: {item.status}")
    bits.append(f"your rating: {item.rating}/5" if item.rating else "your rating: none")
    if media and media.vote_average is not None:
        bits.append(f"TMDB: {media.vote_average}/10")
    if item.platform:
        bits.append(f"on {item.platform}")
    if item.genres:
        bits.append(", ".join(item.genres))
    return " · ".join(bits)


def _bare_title(title: str) -> str:
    """The title without a trailing year, lowercased, for text matching."""
    return re.sub(r"\s*\(\d{4}\)\s*$", "", title).strip().lower()


def _mentions(text: str, title: str) -> bool:
    """Whether `text` refers to `title`.

    Word-boundary matched rather than a plain substring test, so "Up" does not
    match "upcoming" and "It" does not match half the sentence.
    """
    bare = _bare_title(title)
    if len(bare) < MIN_TITLE_MATCH:
        return False
    return re.search(rf"\b{re.escape(bare)}\b", text.lower()) is not None


def _trim_candidate(text: str) -> str:
    """Strip leading and trailing question words from an extracted candidate."""
    words = text.split()
    while words and words[0].lower() in _QUESTION_WORDS:
        words.pop(0)
    while words and words[-1].lower() in _QUESTION_WORDS:
        words.pop()
    return " ".join(words).strip(" .?!,:")


def _extract_titles(question: str) -> list[str]:
    """Pull likely title names out of a free-text question.

    Quoted spans first, then capitalised runs. Capitalisation is the signal, so
    an all-lowercase "what is the matrix about?" yields nothing — that is an
    accepted limit rather than a bug: the fallback is that the model answers
    from general knowledge and says the title is not on the watchlist, which is
    still a useful answer. Being wrong in the other direction is worse, because
    a bogus candidate means a wasted TMDB call and irrelevant facts in the
    prompt.
    """
    found = [m.group(1).strip() for m in _QUOTED.finditer(question)]
    for match in _CAPITALISED_RUN.finditer(question):
        candidate = _trim_candidate(match.group(1))
        if candidate and not all(w.lower() in _QUESTION_WORDS for w in candidate.split()):
            found.append(candidate)

    seen: set[str] = set()
    unique = []
    for candidate in found:
        key = candidate.lower()
        if key and key not in seen and len(key) >= 2:
            seen.add(key)
            unique.append(candidate)
    return unique[:EXTERNAL_LIMIT]


def _listing_subject(question: str) -> str | None:
    """The person or character a listing question is about.

    `_extract_titles` keys on capitalisation, which is the right bias when the
    question is about one title — but wrong here, because people type "what
    films have batman in them?" in lower case and mean it. Once the phrasing has
    already identified the question as a list request, whatever survives having
    the question vocabulary removed is the subject.
    """
    words = re.findall(r"[\w'’-]+", question)
    kept = [w for w in words if w.lower() not in _LISTING_NOISE and not w.isdigit()]
    subject = " ".join(kept).strip()
    # Four words is a generous name; more than that means the filter failed to
    # find a subject and is handing back most of the sentence. The length floor
    # catches the opposite failure — a stray two-letter word surviving as a
    # "subject" and sending TMDB a search for "am".
    if not subject or len(subject) < 3 or len(kept) > 4:
        return None
    return subject


def _listing_lookup(question: str) -> list[str]:
    """TMDB results for "what films involve X?", covering people and characters.

    Both are tried because the question rarely says which it means, and the two
    fail cleanly: a character name matches no person (search_person applies a
    popularity floor and returns None for "batman"), while a person's name
    generally does not headline a franchise.
    """
    subject = _listing_subject(question)
    if not subject:
        return []

    blocks = []

    try:
        person = tmdb.search_person(subject, timeout=tmdb.ENRICH_TIMEOUT)
    except Exception:
        logger.exception("Person lookup failed for %r", subject)
        person = None

    def credit_line(credit: dict, with_character: bool) -> str:
        text = credit["title"]
        if credit["year"]:
            text += f" ({credit['year']})"
        if with_character and credit["character"]:
            text += f" as {credit['character']}"
        return text

    # "What did Spielberg direct?" and "what is he in?" are different questions,
    # and a director who cameos in his own films has a long, irrelevant acting
    # list. When the question names one of the two, answer only that one.
    asked_directing = re.search(r"\bdirect(ed|s|or|ing)?\b", question, re.I) is not None
    asked_acting = re.search(r"\b(star|acts?|acted|acting|appear|plays?|played|cast)\w*\b",
                             question, re.I) is not None

    if person:
        show_directed = person["directed"] and (asked_directing or not asked_acting)
        show_acted = person["acted_in"] and (asked_acting or not asked_directing)
        if show_directed:
            listed = ", ".join(credit_line(c, False) for c in person["directed"])
            blocks.append(f"{person['name']} directed: {listed}")
        if show_acted:
            listed = ", ".join(credit_line(c, True) for c in person["acted_in"])
            blocks.append(f"{person['name']} appeared in: {listed}")

    # Only search titles when the subject was not a person. Searching TMDB for
    # a director's name returns documentaries *about* them and shows they merely
    # produced — "Steven Spielberg" yields Animaniacs and Pinky and the Brain —
    # which is noise next to an actual filmography. It also halves the TMDB
    # calls for the common case.
    if blocks:
        return blocks

    try:
        titles = tmdb.search_titles(subject, limit=8, timeout=tmdb.ENRICH_TIMEOUT)
    except Exception:
        logger.exception("Title list lookup failed for %r", subject)
        titles = []

    if titles:
        lines = []
        for t in titles:
            text = f"  {t['title']}"
            if t["year"]:
                text += f" ({t['year']})"
            text += f" · {t['media_type']}"
            if t["vote_average"] is not None:
                text += f" · TMDB: {t['vote_average']}/10"
            lines.append(text)
        blocks.append(f"Titles matching {subject!r}:\n" + "\n".join(lines))

    return blocks


def _external_lookup(question: str, watchlist: list[models.WatchlistItem]) -> list[str]:
    """TMDB facts for titles named in the question but absent from the watchlist.

    This is what lets the assistant answer "what is The Matrix about?" for a
    film the user does not track, without inventing anything: the answer is
    grounded in a real TMDB record rather than in model recall.

    Best-effort throughout. A missing key, a timeout, or no match simply means
    no external block, and the model falls back to saying so.
    """
    lines = []
    for candidate in _extract_titles(question):
        if any(_bare_title(item.title) == candidate.lower() for item in watchlist):
            continue  # already covered by INDEX, and far better data
        try:
            data = tmdb.search(candidate, timeout=tmdb.ENRICH_TIMEOUT)
        except tmdb.TMDBError as exc:
            logger.info("No TMDB match for %r: %s", candidate, str(exc).splitlines()[0])
            continue
        except Exception:
            logger.exception("TMDB lookup failed for %r", candidate)
            continue

        bits = [data["title"]]
        if data.get("year"):
            bits.append(f"({data['year']})")
        bits.append(data.get("media_type") or "")
        if data.get("runtime_minutes"):
            bits.append(f"{data['runtime_minutes']} min")
        if data.get("vote_average") is not None:
            bits.append(f"TMDB: {data['vote_average']}/10")
        if data.get("genres"):
            bits.append(", ".join(data["genres"]))
        header = " · ".join(b for b in bits if b)
        lines.append(f"{header}\n  {data.get('synopsis') or 'No synopsis available.'}")
    return lines


def _build_context(db: Session, user: models.User, question: str) -> str:
    """Everything Gemini is allowed to answer from, assembled without a network call."""
    items = (
        db.query(models.WatchlistItem)
        .filter(models.WatchlistItem.user_id == user.id)
        .order_by(models.WatchlistItem.title)
        .limit(INDEX_LIMIT)
        .all()
    )
    if not items:
        blocks = ["WATCHLIST", "", "INDEX (complete): (empty — this user tracks no titles yet)"]
        external = _external_lookup(question, [])
        if external:
            blocks += ["", "NOT ON THE WATCHLIST (looked up on TMDB):"] + external
        if _LISTING_INTENT.search(question):
            listing = _listing_lookup(question)
            if listing:
                blocks += ["", "TMDB SEARCH RESULTS (mostly not on the watchlist):"] + listing
        return "\n".join(blocks)

    index = "\n".join(_describe(item) for item in items)

    # Which titles get their synopsis. Two sources, because they fail in
    # opposite directions: embedding search is what makes mood questions work
    # but can rank a directly-named title low, while a name check is exact but
    # blind to anything phrased by theme.
    detail_items: dict[int, models.WatchlistItem] = {
        item.id: item for item in items if _mentions(question, item.title)
    }

    linked = [item for item in items if item.media_id and item.media]
    if linked:
        try:
            ranked = embeddings.find_similar(
                question, [item.media for item in linked], limit=DETAIL_LIMIT
            )
            by_media = {item.media_id: item for item in linked}
            for media_id, _score in ranked:
                item = by_media.get(media_id)
                if item is not None:
                    detail_items.setdefault(item.id, item)
        except embeddings.EmbeddingsUnavailable as exc:
            # Costs nuance on mood questions; the index still answers the
            # factual ones, so this is a degradation rather than a failure.
            logger.info("Semantic search unavailable: %s", str(exc).splitlines()[0])

    blocks = ["WATCHLIST", "", "INDEX (complete):", index]

    detail_lines = []
    for item in list(detail_items.values())[:DETAIL_LIMIT]:
        synopsis = item.synopsis or (item.media.synopsis if item.media else None)
        if not synopsis:
            continue
        parts = [f"{item.title}:"]
        if item.runtime_minutes:
            parts.append(f"[{item.runtime_minutes} min]")
        parts.append(synopsis)
        detail_lines.append(" ".join(parts))

    if detail_lines:
        blocks += ["", "DETAIL (synopses for titles related to the question):"]
        blocks += detail_lines

    external = _external_lookup(question, items)
    if external:
        blocks += ["", "NOT ON THE WATCHLIST (looked up on TMDB):"] + external

    if _LISTING_INTENT.search(question):
        listing = _listing_lookup(question)
        if listing:
            blocks += ["", "TMDB SEARCH RESULTS (mostly not on the watchlist):"] + listing

    return "\n".join(blocks)


def _sources_from_answer(answer: str, db: Session, user: models.User) -> list[dict]:
    """The watchlist items the answer actually names.

    Derived from the finished answer rather than from what retrieval fetched.
    Retrieval deliberately over-supplies — the whole index goes into every
    prompt — so reporting what it gathered would credit every title on the list
    for every question. What the answer mentions is the honest attribution.
    """
    items = (
        db.query(models.WatchlistItem)
        .filter(models.WatchlistItem.user_id == user.id)
        .all()
    )
    sources = []
    for item in items:
        if not _mentions(answer, item.title):
            continue
        year = None if item.year and f"({item.year})" in item.title else item.year
        sources.append({"id": item.id, "title": item.title, "year": year})
    return sources


def _explain(exc: Exception) -> str:
    """Turn an SDK exception into one line a person can act on.

    The raw exceptions are large JSON blobs — useful in a log, unreadable in a
    chat panel. What matters to the reader is only whether to wait and retry or
    to go and fix something, so that is the distinction this draws.
    """
    status = getattr(exc, "code", None) or getattr(exc, "status_code", None)

    if status == 429:
        logger.warning("Gemini quota exhausted on every model: %s", exc)
        return (
            "Rate limit reached on every available model. The free tier allows only a "
            "few requests a minute — wait a minute and ask again."
        )
    if status == 503 or (isinstance(status, int) and status >= 500):
        logger.warning("Gemini unavailable (%s): %s", status, exc)
        return "Gemini is busy right now. Try again in a moment."
    if status == 404:
        logger.error("No usable Gemini model in %s: %s", list(MODELS), exc)
        return (
            f"None of the configured models are available on this key ({', '.join(MODELS)}). "
            "Set GEMINI_MODEL in backend/.env to one that is."
        )
    if status in (401, 403):
        logger.error("Gemini rejected the credential: %s", exc)
        return "Gemini rejected the API key. Check GEMINI_API_KEY in backend/.env."

    logger.exception("Gemini call failed")
    return "The assistant is unavailable right now."


def _to_history(history) -> list[types.Content]:
    """Prior turns in the shape Gemini expects.

    The API contract with the frontend uses "assistant", matching how the rest
    of the world names it; Gemini calls the same role "model". Translating here
    keeps that vocabulary out of the schema and the UI.
    """
    return [
        types.Content(
            role="model" if turn["role"] == "assistant" else "user",
            parts=[types.Part(text=turn["content"])],
        )
        for turn in (history or [])
    ]


def _generate(client: genai.Client, prompt: str, history) -> types.GenerateContentResponse:
    """Send the prompt, moving to the next model only when one is rate-limited.

    A 429 says this model's allowance is spent, which the next model's is not.
    Anything else — a bad key, an unknown model, a server fault — would fail
    identically on every entry, so it is raised immediately rather than retried
    two more times to reach the same conclusion slower.
    """
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )

    last: Exception | None = None
    for model in MODELS:
        try:
            chat = client.chats.create(model=model, config=config, history=_to_history(history))
            return chat.send_message(prompt)
        except Exception as exc:
            if getattr(exc, "code", None) != 429:
                raise
            logger.info("%s is rate-limited, trying the next model", model)
            last = exc

    raise last  # every model exhausted; _explain turns this into the 429 message


def ask(db: Session, user: models.User, question: str, history=None) -> tuple[str, list[dict]]:
    """Answer `question` about `user`'s watchlist in a single API request.

    Returns (answer, sources) where sources are the watchlist items the answer
    names, so the UI can show what it was built from.

    Raises AssistantUnavailable when the assistant cannot run; the router turns
    that into a note rather than an error, so the page stays usable.
    """
    client = _client()
    context = _build_context(db, user, question)
    prompt = f"{context}\n\nQuestion: {question}"

    try:
        response = _generate(client, prompt, history)
    except Exception as exc:
        raise AssistantUnavailable(_explain(exc)) from exc

    # A safety filter on the prompt returns a response with no candidates at
    # all, so this has to be checked before anything reads .text.
    blocked = getattr(getattr(response, "prompt_feedback", None), "block_reason", None)
    if blocked:
        return ("I can't answer that one. Try rephrasing it.", [])

    answer = (response.text or "").strip()
    if not answer:
        finish = None
        if getattr(response, "candidates", None):
            finish = getattr(response.candidates[0], "finish_reason", None)
        logger.warning("Assistant produced no text (finish_reason=%s)", finish)
        return ("I couldn't work that one out. Try asking it a different way.", [])

    return (answer, _sources_from_answer(answer, db, user))
