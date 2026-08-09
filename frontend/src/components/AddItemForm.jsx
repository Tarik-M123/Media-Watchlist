import { useState } from 'react'
import { api } from '../api'
import { STATUS_META, STATUS_ORDER } from '../constants'
import StarRating from './StarRating'
import TitleSearchField from './TitleSearchField'

const EMPTY = {
  title: '',
  platform: '',
  status: 'planning_to_watch',
  rating: null,
  tmdb_id: null,
  media_type: null,
}

// Sentinel for the escape hatch in the platform dropdown. Not a platform name,
// so it can never collide with one TMDB returns.
const OTHER = '__other__'

export default function AddItemForm({ onCreate }) {
  const [form, setForm] = useState(EMPTY)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [platforms, setPlatforms] = useState([])
  const [manualPlatform, setManualPlatform] = useState(true)
  const [platformNote, setPlatformNote] = useState(null)

  function update(patch) {
    setForm((f) => ({ ...f, ...patch }))
  }

  function changeTitle(title) {
    // Editing the title after picking must drop the stored identity, or the
    // item would be saved carrying a different show's tmdb_id.
    update({ title, tmdb_id: null, media_type: null })
  }

  async function pickTitle(candidate) {
    update({ tmdb_id: candidate.tmdb_id, media_type: candidate.media_type })
    setPlatforms([])
    setPlatformNote(null)
    try {
      const data = await api.watchProviders(candidate.media_type, candidate.tmdb_id)
      setPlatforms(data.streaming)
      if (data.streaming.length > 0) {
        setManualPlatform(false)
        update({ platform: data.streaming[0] })
      } else {
        // Availability is region-specific and smaller markets have real gaps,
        // so "nothing found" is ordinary — fall back to typing rather than
        // showing an empty dropdown.
        setManualPlatform(true)
        setPlatformNote(
          data.unavailable ?? `No streaming info for your region (${data.region}) — type it in.`,
        )
      }
    } catch {
      setManualPlatform(true)
    }
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
        tmdb_id: form.tmdb_id,
        media_type: form.media_type,
      })
      setForm(EMPTY)
      setPlatforms([])
      setManualPlatform(true)
      setPlatformNote(null)
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
          <label htmlFor="title" className="block text-xs font-medium text-slate-500 dark:text-slate-400">
            Title
          </label>
          <TitleSearchField
            value={form.title}
            onChange={changeTitle}
            onPick={pickTitle}
            disabled={busy}
          />
        </div>

        <div className="flex-1">
          <label htmlFor="platform" className="block text-xs font-medium text-slate-500 dark:text-slate-400">
            Platform
          </label>
          {manualPlatform ? (
            <input
              id="platform"
              value={form.platform}
              onChange={(e) => update({ platform: e.target.value })}
              placeholder="Apple TV+"
              className="mt-1 w-full rounded-lg border border-slate-400 bg-white px-3 py-2 text-sm outline-none placeholder-slate-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 dark:border-slate-700 dark:bg-slate-950 dark:placeholder-slate-600"
            />
          ) : (
            <select
              id="platform"
              value={form.platform}
              onChange={(e) => {
                if (e.target.value === OTHER) {
                  setManualPlatform(true)
                  update({ platform: '' })
                } else {
                  update({ platform: e.target.value })
                }
              }}
              className="mt-1 w-full rounded-lg border border-slate-400 bg-white px-3 py-2 text-sm outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 dark:border-slate-700 dark:bg-slate-950"
            >
              {platforms.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
              <option value={OTHER}>Other…</option>
            </select>
          )}
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

      {platformNote && (
        <p className="mt-2 text-xs text-slate-500">{platformNote}</p>
      )}

      {platforms.length > 0 && !manualPlatform && (
        // TMDB's terms require crediting JustWatch wherever provider data is shown.
        <p className="mt-2 text-xs text-slate-500">
          Streaming availability for your region, via TMDB and JustWatch.
        </p>
      )}

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
