export const STATUS_ORDER = [
  'planning_to_watch',
  'watching',
  'finished',
  'dropped',
]

// Class strings are written out in full — Tailwind scans source text, so
// names built at runtime (`bg-${colour}-400`) would never be generated.
// Each entry carries its light value first and the dark: variant after; the
// 300-level text used in dark mode washes out badly on a white card.
export const STATUS_META = {
  planning_to_watch: {
    label: 'Planning to Watch',
    dot: 'bg-sky-500 dark:bg-sky-400',
    chip: 'bg-sky-500/10 text-sky-700 ring-1 ring-sky-500/30 dark:text-sky-300',
    stat: 'text-sky-700 dark:text-sky-300',
  },
  watching: {
    label: 'Watching',
    dot: 'bg-amber-500 dark:bg-amber-400',
    chip: 'bg-amber-500/10 text-amber-700 ring-1 ring-amber-500/30 dark:text-amber-300',
    stat: 'text-amber-700 dark:text-amber-300',
  },
  finished: {
    label: 'Finished',
    dot: 'bg-emerald-500 dark:bg-emerald-400',
    chip: 'bg-emerald-500/10 text-emerald-700 ring-1 ring-emerald-500/30 dark:text-emerald-300',
    stat: 'text-emerald-700 dark:text-emerald-300',
  },
  dropped: {
    label: 'Dropped',
    dot: 'bg-rose-500 dark:bg-rose-400',
    chip: 'bg-rose-500/10 text-rose-700 ring-1 ring-rose-500/30 dark:text-rose-300',
    stat: 'text-rose-700 dark:text-rose-300',
  },
}
