import { useState } from 'react'
import { STATUS_META, STATUS_ORDER } from '../constants'
import StarRating from './StarRating'

export default function ItemCard({ item, onUpdate, onDelete }) {
  // Set when the user picks "finished" on an item that has no rating yet —
  // the API refuses that combination, so we collect the rating first and
  // send status + rating together.
  const [awaitingRating, setAwaitingRating] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [pendingStatusChange, setPendingStatusChange] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  async function run(fn) {
    setError(null)
    setBusy(true)
    try {
      await fn()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  function changeStatus(next) {
    setAwaitingRating(false)
    if (next === item.status) return
    if (next === 'finished' && item.rating == null) {
      setAwaitingRating(true)
      return
    }
    if (item.status === 'finished' && item.rating != null && next !== 'finished') {
      setPendingStatusChange(next)
      return
    }
    run(() => onUpdate(item.id, { status: next }))
  }

  function confirmStatusChange() {
    if (pendingStatusChange) {
      setPendingStatusChange(null)
      run(() => onUpdate(item.id, { status: pendingStatusChange }))
    }
  }

  function rate(rating) {
    setAwaitingRating(false)
    run(() => onUpdate(item.id, { status: 'finished', rating }))
  }

  const showStars = item.status === 'finished' || awaitingRating

  return (
    <div className="rounded-xl border border-slate-300 bg-white p-4 shadow-sm transition hover:border-slate-400 dark:border-slate-800 dark:bg-slate-900/60 dark:shadow-none dark:hover:border-slate-700">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="truncate font-medium text-slate-900 dark:text-slate-100" title={item.title}>
            {item.title}
          </h3>
          <p className="mt-0.5 truncate text-xs text-slate-500">{item.platform}</p>
        </div>
        <span
          className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium ${STATUS_META[item.status].chip}`}
        >
          {STATUS_META[item.status].label}
        </span>
      </div>

      {showStars && (
        <div className="mt-3 flex items-center gap-2">
          <StarRating value={item.rating} onRate={rate} disabled={busy} />
          {awaitingRating && (
            <span className="text-[11px] text-amber-700 dark:text-amber-300">
              Pick a rating to finish
            </span>
          )}
        </div>
      )}

      {pendingStatusChange && (
        <div className="mt-3 rounded-lg bg-amber-500/10 border border-amber-500/30 px-3 py-2 text-xs text-amber-700 dark:text-amber-200">
          This will clear your {item.rating}-star rating. Continue?
        </div>
      )}

      <div className="mt-3 flex items-center gap-2 border-t border-slate-200 pt-3 dark:border-slate-800">
        <select
          value={awaitingRating ? 'finished' : item.status}
          disabled={busy || pendingStatusChange}
          onChange={(e) => changeStatus(e.target.value)}
          className="flex-1 rounded-lg border border-slate-400 bg-white px-2 py-1.5 text-xs outline-none focus:border-indigo-500 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-950"
        >
          {STATUS_ORDER.map((s) => (
            <option key={s} value={s}>
              {STATUS_META[s].label}
            </option>
          ))}
        </select>

        {pendingStatusChange ? (
          <>
            <button
              onClick={confirmStatusChange}
              disabled={busy}
              className="rounded-lg bg-amber-600 px-2.5 py-1.5 text-xs font-medium text-white transition hover:bg-amber-500 disabled:opacity-50"
            >
              Confirm
            </button>
            <button
              onClick={() => setPendingStatusChange(null)}
              disabled={busy}
              className="rounded-lg border border-slate-400 px-2.5 py-1.5 text-xs text-slate-700 transition hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
            >
              Cancel
            </button>
          </>
        ) : confirmDelete ? (
          <>
            <button
              onClick={() => run(() => onDelete(item.id))}
              disabled={busy}
              className="rounded-lg bg-rose-600 px-2.5 py-1.5 text-xs font-medium text-white transition hover:bg-rose-500 disabled:opacity-50"
            >
              Confirm
            </button>
            <button
              onClick={() => setConfirmDelete(false)}
              className="rounded-lg border border-slate-400 px-2.5 py-1.5 text-xs text-slate-700 transition hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
            >
              Cancel
            </button>
          </>
        ) : (
          <button
            onClick={() => setConfirmDelete(true)}
            disabled={busy}
            aria-label={`Delete ${item.title}`}
            className="rounded-lg border border-slate-400 px-2.5 py-1.5 text-xs text-slate-600 transition hover:border-rose-400 hover:text-rose-600 disabled:opacity-50 dark:border-slate-700 dark:text-slate-400 dark:hover:border-rose-700 dark:hover:text-rose-300"
          >
            Delete
          </button>
        )}
      </div>

      {error && <p className="mt-2 text-xs text-rose-600 dark:text-rose-300">{error}</p>}
    </div>
  )
}
