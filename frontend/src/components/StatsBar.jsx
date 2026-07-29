import { STATUS_META, STATUS_ORDER } from '../constants'

export default function StatsBar({ stats }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
      {STATUS_ORDER.map((status) => (
        <div
          key={status}
          className="rounded-xl border border-slate-800 bg-slate-900/60 p-4"
        >
          <div className="flex items-center gap-2">
            <span className={`h-2 w-2 rounded-full ${STATUS_META[status].dot}`} />
            <span className="text-xs font-medium text-slate-400">
              {STATUS_META[status].label}
            </span>
          </div>
          <p className={`mt-2 text-2xl font-semibold ${STATUS_META[status].stat}`}>
            {stats[status]}
          </p>
        </div>
      ))}

      <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-slate-500" />
          <span className="text-xs font-medium text-slate-400">Total</span>
        </div>
        <p className="mt-2 text-2xl font-semibold text-slate-100">{stats.total}</p>
      </div>
    </div>
  )
}
