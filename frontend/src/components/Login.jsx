import { useState } from 'react'
import { api } from '../api'

export default function Login({ onAuth }) {
  const [email, setEmail] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  async function submit(mode) {
    if (!email.trim()) {
      setError('Enter an email address first.')
      return
    }
    setError(null)
    setBusy(true)
    try {
      const result =
        mode === 'login' ? await api.login(email.trim()) : await api.register(email.trim())
      onAuth(result)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-svh items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <h1 className="text-2xl font-semibold tracking-tight text-white">
            Media Watchlist
          </h1>
          <p className="mt-2 text-sm text-slate-400">
            Track what you're watching, across every platform.
          </p>
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault()
            submit('login')
          }}
          className="rounded-xl border border-slate-800 bg-slate-900/60 p-6 shadow-xl"
        >
          <label htmlFor="email" className="block text-sm font-medium text-slate-300">
            Email address
          </label>
          <input
            id="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            autoComplete="email"
            className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 placeholder-slate-600 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
          />

          {error && (
            <p className="mt-3 rounded-lg bg-rose-500/10 px-3 py-2 text-sm text-rose-300 ring-1 ring-rose-500/30">
              {error}
            </p>
          )}

          <div className="mt-5 flex gap-3">
            <button
              type="submit"
              disabled={busy}
              className="flex-1 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-500 disabled:opacity-50"
            >
              {busy ? 'Please wait…' : 'Log in'}
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => submit('register')}
              className="flex-1 rounded-lg border border-slate-700 px-4 py-2 text-sm font-medium text-slate-200 transition hover:bg-slate-800 disabled:opacity-50"
            >
              Register
            </button>
          </div>
        </form>

        <p className="mt-4 text-center text-xs text-slate-500">
          New here? Enter an email and choose Register.
        </p>
      </div>
    </div>
  )
}
