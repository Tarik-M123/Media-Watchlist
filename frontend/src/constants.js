export const STATUS_ORDER = [
  'planning_to_watch',
  'watching',
  'finished',
  'dropped',
]

// Class strings are written out in full — Tailwind scans source text, so
// names built at runtime (`bg-${colour}-400`) would never be generated.
export const STATUS_META = {
  planning_to_watch: {
    label: 'Planning to Watch',
    dot: 'bg-sky-400',
    chip: 'bg-sky-500/10 text-sky-300 ring-1 ring-sky-500/30',
    stat: 'text-sky-300',
  },
  watching: {
    label: 'Watching',
    dot: 'bg-amber-400',
    chip: 'bg-amber-500/10 text-amber-300 ring-1 ring-amber-500/30',
    stat: 'text-amber-300',
  },
  finished: {
    label: 'Finished',
    dot: 'bg-emerald-400',
    chip: 'bg-emerald-500/10 text-emerald-300 ring-1 ring-emerald-500/30',
    stat: 'text-emerald-300',
  },
  dropped: {
    label: 'Dropped',
    dot: 'bg-rose-400',
    chip: 'bg-rose-500/10 text-rose-300 ring-1 ring-rose-500/30',
    stat: 'text-rose-300',
  },
}
