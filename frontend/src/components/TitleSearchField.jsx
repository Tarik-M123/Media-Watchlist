// Title input that suggests real shows from TMDB and reports the one picked.
import { useEffect, useId, useRef, useState } from 'react'
import { api } from '../api'
import MediaImage from './MediaImage'

const MIN_QUERY = 2
const DEBOUNCE_MS = 300

export default function TitleSearchField({ value, onChange, onPick, disabled = false }) {
  const [results, setResults] = useState([])
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)
  const [note, setNote] = useState(null)

  // Set when a suggestion is chosen, so the effect below can tell "the user is
  // typing" from "we just filled the box in" and skip searching for our own text.
  const justPicked = useRef(false)
  const listId = useId()
  const boxRef = useRef(null)

  useEffect(() => {
    if (justPicked.current) {
      justPicked.current = false
      return
    }
    const query = value.trim()
    if (query.length < MIN_QUERY) {
      setResults([])
      setOpen(false)
      setNote(null)
      return
    }

    // One request per pause in typing, not one per keystroke.
    const controller = new AbortController()
    const timer = setTimeout(async () => {
      try {
        const data = await api.searchMedia(query, controller.signal)
        setResults(data.results)
        setNote(data.unavailable ?? null)
        setActive(-1)
        setOpen(data.results.length > 0 || !!data.unavailable)
      } catch (e) {
        // Aborted means a newer keystroke superseded this request; anything else
        // just means no suggestions, which must never block typing a title.
        if (e.name !== 'AbortError') {
          setResults([])
          setOpen(false)
        }
      }
    }, DEBOUNCE_MS)

    // Cleanup runs before the next effect, so an in-flight request for stale
    // text can never overwrite results for newer text.
    return () => {
      clearTimeout(timer)
      controller.abort()
    }
  }, [value])

  function choose(candidate) {
    justPicked.current = true
    onChange(candidate.title)
    onPick(candidate)
    setOpen(false)
    setResults([])
    setActive(-1)
  }

  function onKeyDown(e) {
    if (!open || results.length === 0) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActive((i) => (i + 1) % results.length)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActive((i) => (i <= 0 ? results.length - 1 : i - 1))
    } else if (e.key === 'Enter' && active >= 0) {
      // Only swallow Enter when a suggestion is highlighted, so Enter still
      // submits the form for someone who ignored the list.
      e.preventDefault()
      choose(results[active])
    } else if (e.key === 'Escape') {
      setOpen(false)
    }
  }

  return (
    <div ref={boxRef} className="relative">
      <input
        id="title"
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={onKeyDown}
        onFocus={() => results.length > 0 && setOpen(true)}
        // A click on a suggestion fires after blur, so closing is deferred a
        // tick — otherwise the list disappears before the click lands.
        onBlur={() => setTimeout(() => setOpen(false), 120)}
        placeholder="Severance"
        autoComplete="off"
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={active >= 0 ? `${listId}-${active}` : undefined}
        className="mt-1 w-full rounded-lg border border-slate-400 bg-white px-3 py-2 text-sm outline-none placeholder-slate-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 dark:border-slate-700 dark:bg-slate-950 dark:placeholder-slate-600"
      />

      {open && (
        <ul
          id={listId}
          role="listbox"
          className="absolute z-20 mt-1 max-h-72 w-full overflow-y-auto rounded-lg border border-slate-300 bg-white py-1 shadow-lg dark:border-slate-700 dark:bg-slate-900"
        >
          {note && (
            <li className="px-3 py-2 text-xs text-slate-500">{note}</li>
          )}
          {results.map((candidate, i) => (
            <li
              key={`${candidate.media_type}-${candidate.tmdb_id}`}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === active}
              onMouseEnter={() => setActive(i)}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => choose(candidate)}
              className={`flex cursor-pointer items-center gap-3 px-3 py-2 ${
                i === active ? 'bg-indigo-50 dark:bg-slate-800' : ''
              }`}
            >
              <MediaImage src={candidate.poster_thumb} title={candidate.title} size="thumb" />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm text-slate-900 dark:text-slate-100">
                  {candidate.title}
                </span>
                <span className="block text-xs text-slate-500">
                  {[
                    candidate.year,
                    candidate.media_type === 'tv' ? 'TV series' : 'Film',
                    candidate.vote_average ? `★ ${candidate.vote_average}` : null,
                  ]
                    .filter(Boolean)
                    .join(' · ')}
                </span>
                {/* Two films can share a title and a year — TMDB lists two 2026
                    releases called "The Odyssey" — so one line of synopsis is
                    what makes the rows tellable apart. Truncated to one line:
                    the list is capped at max-h-72 and rows must not grow. */}
                {candidate.synopsis && (
                  <span className="block truncate text-xs text-slate-400 dark:text-slate-500">
                    {candidate.synopsis}
                  </span>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
