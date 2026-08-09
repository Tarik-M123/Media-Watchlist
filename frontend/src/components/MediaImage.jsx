// Poster image for a watchlist item, with a placeholder tile when there is no art.
import { useEffect, useState } from 'react'

// Written out in full rather than built at runtime — Tailwind only sees
// complete literal strings in source.
const SIZES = {
  // Deliberately small: the dashboard is a 4-column grid at xl, so every pixel
  // the poster takes comes straight out of the title.
  card: 'w-12 sm:w-14',
  large: 'w-40 sm:w-56',
  thumb: 'w-8',
}

const INITIAL_TEXT = {
  card: 'text-base',
  large: 'text-5xl',
  thumb: 'text-[11px]',
}

export default function MediaImage({ src, title, size = 'card' }) {
  const [failed, setFailed] = useState(false)

  // TMDB paths change and scraped URLs expire, so a src that worked last week
  // can 404 today. Reset on src change or a retry would never re-attempt.
  useEffect(() => {
    setFailed(false)
  }, [src])

  const showPlaceholder = !src || failed

  return (
    <div
      className={`${SIZES[size]} shrink-0 overflow-hidden rounded-lg border border-slate-300 bg-slate-100 dark:border-slate-700 dark:bg-slate-800`}
    >
      {/* Fixed 2:3 ratio in both branches so the grid does not reflow as
          images arrive. */}
      {showPlaceholder ? (
        <div
          className="flex aspect-[2/3] items-center justify-center"
          role="img"
          aria-label={`No poster available for ${title}`}
        >
          <span className={`${INITIAL_TEXT[size]} font-semibold text-slate-400 dark:text-slate-500`}>
            {title?.trim()?.[0]?.toUpperCase() ?? '?'}
          </span>
        </div>
      ) : (
        <img
          src={src}
          alt={`Poster for ${title}`}
          loading="lazy"
          onError={() => setFailed(true)}
          className="aspect-[2/3] h-full w-full object-cover"
        />
      )}
    </div>
  )
}
