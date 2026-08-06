import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import { STATUS_META, STATUS_ORDER } from '../constants'
import AddItemForm from './AddItemForm'
import Clock from './Clock'
import ItemCard from './ItemCard'
import StatsBar from './StatsBar'
import ThemeToggle from './ThemeToggle'

export default function Dashboard({ user, onLogout }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    try {
      setError(null)
      setData(await api.dashboard())
    } catch (e) {
      // A dead token can only be cleared by signing out again.
      if (e.status === 401) {
        onLogout()
        return
      }
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [onLogout])

  useEffect(() => {
    load()
  }, [load])

  // Each mutation refetches, so the stats and the grouping stay in step with
  // the server rather than being recomputed here and drifting.
  async function createItem(item) {
    await api.createItem(item)
    await load()
  }

  async function updateItem(id, patch) {
    await api.updateItem(id, patch)
    await load()
  }

  async function deleteItem(id) {
    await api.deleteItem(id)
    await load()
  }

  return (
    <div className="mx-auto max-w-7xl px-4 py-8">
      <header className="mb-8 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-slate-900 dark:text-white">
            Media Watchlist
          </h1>
          <p className="mt-0.5 text-sm text-slate-500">{user.email}</p>
        </div>

        {/* ml-auto keeps the controls right-aligned when the header wraps at
            narrow widths — justify-between resolves to flex-start once they
            are the only item on their line. */}
        <div className="ml-auto flex items-center gap-2">
          <Clock />
          <ThemeToggle />
          <button
            onClick={onLogout}
            className="rounded-lg border border-slate-400 bg-white px-3 py-1.5 text-sm text-slate-700 transition hover:bg-slate-100 dark:border-slate-700 dark:bg-transparent dark:text-slate-300 dark:hover:bg-slate-800"
          >
            Log out
          </button>
        </div>
      </header>

      {loading && <p className="text-sm text-slate-500">Loading…</p>}

      {error && (
        <div className="mb-6 rounded-lg bg-rose-500/10 px-4 py-3 text-sm text-rose-700 ring-1 ring-rose-500/30 dark:text-rose-300">
          {error}{' '}
          <button onClick={load} className="ml-2 underline hover:no-underline">
            Retry
          </button>
        </div>
      )}

      {data && (
        <div className="space-y-6">
          <StatsBar stats={data.stats} />

          <AddItemForm onCreate={createItem} />

          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            {STATUS_ORDER.map((status) => (
              <section key={status}>
                <div className="mb-3 flex items-center gap-2">
                  <span className={`h-2 w-2 rounded-full ${STATUS_META[status].dot}`} />
                  <h2 className="text-sm font-medium text-slate-700 dark:text-slate-300">
                    {STATUS_META[status].label}
                  </h2>
                  <span className="text-xs text-slate-400 dark:text-slate-600">
                    {data.items[status]?.length ?? 0}
                  </span>
                </div>

                <div className="space-y-3">
                  {(data.items[status] ?? []).map((item) => (
                    <ItemCard
                      key={item.id}
                      item={item}
                      onUpdate={updateItem}
                      onDelete={deleteItem}
                    />
                  ))}

                  {(data.items[status] ?? []).length === 0 && (
                    <p className="rounded-xl border border-dashed border-slate-400 px-4 py-6 text-center text-xs text-slate-500 dark:border-slate-800 dark:text-slate-500">
                      Nothing here yet
                    </p>
                  )}
                </div>
              </section>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
