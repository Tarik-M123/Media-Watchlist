// Current date and time in the top corner, so the date is visible while using the app.
import { useEffect, useState } from 'react'

const DATE_FORMAT = { weekday: 'short', day: 'numeric', month: 'short' }
const TIME_FORMAT = { hour: '2-digit', minute: '2-digit' }

export default function Clock() {
  const [now, setNow] = useState(() => new Date())

  useEffect(() => {
    let interval

    // Line up with the wall clock instead of the mount time. A plain 60s
    // interval started at :30 would flip the displayed minute half a minute
    // late, every minute.
    const timeout = setTimeout(() => {
      setNow(new Date())
      interval = setInterval(() => setNow(new Date()), 60000)
    }, 60000 - (Date.now() % 60000))

    // Background tabs get their timers throttled, so a tab left open and
    // returned to would keep showing the time it froze at until the next tick.
    function resync() {
      if (!document.hidden) setNow(new Date())
    }
    document.addEventListener('visibilitychange', resync)

    return () => {
      clearTimeout(timeout)
      clearInterval(interval)
      document.removeEventListener('visibilitychange', resync)
    }
  }, [])

  return (
    <time
      dateTime={now.toISOString()}
      className="hidden text-sm text-slate-600 tabular-nums sm:inline dark:text-slate-400"
    >
      {now.toLocaleDateString(undefined, DATE_FORMAT)}
      <span className="mx-1.5 text-slate-400 dark:text-slate-600">·</span>
      {now.toLocaleTimeString(undefined, TIME_FORMAT)}
    </time>
  )
}
