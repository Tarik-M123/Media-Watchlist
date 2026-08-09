// Full-size view of one watchlist item, opened by clicking its card.
import { useEffect, useRef } from 'react'
import { STATUS_META } from '../constants'
import MediaImage from './MediaImage'
import StarRating from './StarRating'

const FOCUSABLE =
  'a[href], button:not([disabled]), input, select, textarea, [tabindex]:not([tabindex="-1"])'

function formatRuntime(minutes) {
  if (!minutes) return null
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  if (!h) return `${m}m`
  return m ? `${h}h ${m}m` : `${h}h`
}

export default function MediaDetailModal({ item, onClose }) {
  const panelRef = useRef(null)
  const closeRef = useRef(null)

  useEffect(() => {
    // Remember who opened the dialog so focus can go back there on close —
    // without this, closing drops focus to <body> and keyboard users lose
    // their place in the grid.
    const opener = document.activeElement
    closeRef.current?.focus()

    // Stop the page behind the dialog from scrolling.
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    function onKeyDown(e) {
      if (e.key === 'Escape') {
        onClose()
        return
      }
      if (e.key !== 'Tab') return

      // Focus trap: without it, Tab walks into the cards behind the overlay.
      const focusable = panelRef.current?.querySelectorAll(FOCUSABLE)
      if (!focusable?.length) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      document.body.style.overflow = previousOverflow
      opener?.focus?.()
    }
  }, [onClose])

  const meta = [
    item.year,
    item.media_type === 'tv' ? 'TV series' : item.media_type === 'movie' ? 'Film' : null,
    formatRuntime(item.runtime_minutes),
  ].filter(Boolean)

  return (
    <div
      onClick={onClose}
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-sm dark:bg-slate-950/80"
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="media-detail-title"
        // The backdrop closes on click; clicks inside the panel must not
        // bubble up to it.
        onClick={(e) => e.stopPropagation()}
        className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-xl border border-slate-300 bg-white p-5 shadow-xl dark:border-slate-800 dark:bg-slate-900"
      >
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <h2
              id="media-detail-title"
              className="text-lg font-semibold text-slate-900 dark:text-white"
            >
              {item.title}
            </h2>
            <p className="mt-0.5 text-sm text-slate-500">{item.platform}</p>
          </div>
          <button
            ref={closeRef}
            onClick={onClose}
            aria-label="Close details"
            className="shrink-0 rounded-lg border border-slate-400 px-2.5 py-1.5 text-xs text-slate-700 transition hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            Close
          </button>
        </div>

        <div className="mt-4 flex flex-col gap-5 sm:flex-row">
          <MediaImage src={item.poster_url_large || item.poster_url} title={item.title} size="large" />

          <div className="min-w-0 flex-1">
            <span
              className={`inline-block rounded-full px-2 py-0.5 text-[11px] font-medium ${STATUS_META[item.status].chip}`}
            >
              {STATUS_META[item.status].label}
            </span>

            {meta.length > 0 && (
              <p className="mt-3 text-sm text-slate-600 dark:text-slate-400">{meta.join(' · ')}</p>
            )}

            {item.genres?.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-1.5">
                {item.genres.map((genre) => (
                  <span
                    key={genre}
                    className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] text-slate-700 dark:bg-slate-800 dark:text-slate-300"
                  >
                    {genre}
                  </span>
                ))}
              </div>
            )}

            {item.status === 'finished' && item.rating != null && (
              <div className="mt-4">
                <p className="text-xs font-medium text-slate-500 dark:text-slate-400">Your rating</p>
                <div className="mt-1">
                  {/* Read-only here: the card is where ratings are changed. */}
                  <StarRating value={item.rating} onRate={() => {}} disabled />
                </div>
              </div>
            )}

            {item.synopsis && (
              <p className="mt-4 text-sm leading-relaxed text-slate-700 dark:text-slate-300">
                {item.synopsis}
              </p>
            )}

            {!item.synopsis && !item.genres?.length && meta.length === 0 && (
              <p className="mt-4 text-sm text-slate-500">
                No details yet — this item has no TMDB metadata.
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
