import { useState } from 'react'
import { STATUS_META, STATUS_ORDER } from '../constants'
import StarRating from './StarRating'

const EMPTY = { title: '', platform: '', status: 'planning_to_watch', rating: null }

export default function AddItemForm({ onCreate }) {
  const [form, setForm] = useState(EMPTY)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  function update(patch) {
    setForm((f) => ({ ...f, ...patch }))
  }

  async function submit(e) {
    e.preventDefault()
    if (!form.title.trim() || !form.platform.trim()) {
      setError('Title and platform are both required.')
      return
    }
    // The API rejects `finished` without a rating — catch it here so the
    // user gets an inline hint instead of a round-trip 422.
    if (form.status === 'finished' && form.rating == null) {
      setError('Pick a rating before marking something as finished.')
      return
    }

    setError(null)
    setBusy(true)
    try {
      await onCreate({
        title: form.title.trim(),
        platform: form.platform.trim(),
        status: form.status,
        rating: form.status === 'finished' ? form.rating : null,
      })
      setForm(EMPTY)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form
      onSubmit={submit}
      className="rounded-xl border border-slate-300 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900/60 dark:shadow-none"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <div className="flex-1">
          <label className="block text-xs font-medium text-slate-500 dark:text-slate-400">Title</label>
          <input
            value={form.title}
            onChange={(e) => update({ title: e.target.value })}
            placeholder="Severance"
            className="mt-1 w-full rounded-lg border border-slate-400 bg-white px-3 py-2 text-sm outline-none placeholder-slate-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 dark:border-slate-700 dark:bg-slate-950 dark:placeholder-slate-600"
          />
        </div>

        <div className="flex-1">
          <label className="block text-xs font-medium text-slate-500 dark:text-slate-400">Platform</label>
          <input
            value={form.platform}
            onChange={(e) => update({ platform: e.target.value })}
            placeholder="Apple TV+"
            className="mt-1 w-full rounded-lg border border-slate-400 bg-white px-3 py-2 text-sm outline-none placeholder-slate-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 dark:border-slate-700 dark:bg-slate-950 dark:placeholder-slate-600"
          />
        </div>

        <div className="sm:w-48">
          <label className="block text-xs font-medium text-slate-500 dark:text-slate-400">Status</label>
          <select
            value={form.status}
            onChange={(e) =>
              update({
                status: e.target.value,
                rating: e.target.value === 'finished' ? form.rating : null,
              })
            }
            className="mt-1 w-full rounded-lg border border-slate-400 bg-white px-3 py-2 text-sm outline-none placeholder-slate-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 dark:border-slate-700 dark:bg-slate-950 dark:placeholder-slate-600"
          >
            {STATUS_ORDER.map((s) => (
              <option key={s} value={s}>
                {STATUS_META[s].label}
              </option>
            ))}
          </select>
        </div>

        <button
          type="submit"
          disabled={busy}
          className="rounded-lg bg-indigo-600 px-5 py-2 text-sm font-medium text-white transition hover:bg-indigo-500 disabled:opacity-50"
        >
          {busy ? 'Adding…' : 'Add'}
        </button>
      </div>

      {form.status === 'finished' && (
        <div className="mt-3 flex items-center gap-3 border-t border-slate-200 pt-3 dark:border-slate-800">
          <span className="text-xs font-medium text-slate-500 dark:text-slate-400">
            Rating <span className="text-rose-400">*</span>
          </span>
          <StarRating value={form.rating} onRate={(rating) => update({ rating })} />
        </div>
      )}

      {error && (
        <p className="mt-3 rounded-lg bg-rose-500/10 px-3 py-2 text-sm text-rose-700 ring-1 ring-rose-500/30 dark:text-rose-300">
          {error}
        </p>
      )}
    </form>
  )
}
