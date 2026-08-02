export default function StarRating({ value, onRate, disabled = false, size = 'sm' }) {
  const dimension = size === 'lg' ? 'h-6 w-6' : 'h-4 w-4'

  return (
    <div className="flex items-center gap-0.5">
      {[1, 2, 3, 4, 5].map((star) => {
        const filled = value != null && star <= value
        return (
          <button
            key={star}
            type="button"
            disabled={disabled}
            onClick={() => onRate(star)}
            aria-label={`Rate ${star} out of 5`}
            className="rounded p-2 transition disabled:cursor-not-allowed enabled:hover:scale-110"
          >
            <svg
              viewBox="0 0 20 20"
              className={`${dimension} ${filled ? 'text-amber-400' : 'text-slate-700'}`}
              fill="currentColor"
            >
              <path d="M10 1.5l2.6 5.3 5.9.9-4.2 4.1 1 5.8-5.3-2.8-5.3 2.8 1-5.8L1.5 7.7l5.9-.9L10 1.5z" />
            </svg>
          </button>
        )
      })}
    </div>
  )
}
