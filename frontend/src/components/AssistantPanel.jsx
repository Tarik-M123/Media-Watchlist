// Floating chat widget for asking natural-language questions about your watchlist.
import { useEffect, useRef, useState } from 'react'
import { api } from '../api'

// The API caps history at 20 turns and rejects more, so trim here rather than
// letting a long conversation start failing validation.
const MAX_HISTORY = 20

// Semantic search and off-watchlist lookup are the two things nobody guesses a
// text box can do, so the examples lead with them.
const EXAMPLES = [
  'Something slow I haven\'t started',
  'What did I rate 5 stars?',
  'What is The Matrix about?',
]

export default function AssistantPanel() {
  const [open, setOpen] = useState(false)
  const [question, setQuestion] = useState('')
  const [turns, setTurns] = useState([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [unavailable, setUnavailable] = useState(null)

  const inputRef = useRef(null)
  const transcriptRef = useRef(null)

  useEffect(() => {
    if (open) inputRef.current?.focus()
  }, [open])

  // Escape closes the panel, which is the convention for anything that floats
  // above the page.
  useEffect(() => {
    if (!open) return
    function onKey(e) {
      if (e.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  // Pin the transcript to the newest turn; without this a long conversation
  // leaves the answer you are waiting for below the fold.
  useEffect(() => {
    const el = transcriptRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [turns, busy])

  async function ask(e) {
    e.preventDefault()
    const asked = question.trim()
    if (!asked || busy) return

    setError(null)
    setUnavailable(null)
    setBusy(true)
    // Clear the box immediately so the question doesn't sit there looking
    // unsent while the model works.
    setQuestion('')

    const history = turns.slice(-MAX_HISTORY).map(({ role, content }) => ({ role, content }))
    setTurns((t) => [...t, { role: 'user', content: asked }])

    try {
      const data = await api.askAssistant(asked, history)
      if (data.unavailable) {
        setUnavailable(data.unavailable)
        return
      }
      setTurns((t) => [...t, { role: 'assistant', content: data.answer, sources: data.sources }])
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      {open && (
        <div
          role="dialog"
          aria-label="Ask your watchlist"
          // Width is capped by the viewport so the panel never overflows on a
          // phone, where it becomes near-full-width instead.
          className="fixed bottom-20 right-4 z-50 flex w-[min(24rem,calc(100vw-2rem))] flex-col rounded-xl border border-slate-300 bg-white shadow-xl dark:border-slate-800 dark:bg-slate-900"
        >
          <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3 dark:border-slate-800">
            <h2 className="text-sm font-medium text-slate-700 dark:text-slate-300">
              Ask your watchlist
            </h2>
            <button
              type="button"
              onClick={() => setOpen(false)}
              aria-label="Close assistant"
              className="rounded-lg p-1 text-slate-500 transition hover:bg-slate-100 dark:hover:bg-slate-800"
            >
              <svg viewBox="0 0 20 20" className="h-4 w-4" fill="currentColor" aria-hidden="true">
                <path d="M6.28 5.22a.75.75 0 0 0-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 1 0 1.06 1.06L10 11.06l3.72 3.72a.75.75 0 1 0 1.06-1.06L11.06 10l3.72-3.72a.75.75 0 0 0-1.06-1.06L10 8.94 6.28 5.22Z" />
              </svg>
            </button>
          </div>

          <div ref={transcriptRef} className="max-h-[50vh] min-h-[8rem] space-y-3 overflow-y-auto px-4 py-3">
            {turns.length === 0 && (
              <>
                <p className="text-xs text-slate-500">
                  Ask about your list, or about a film that isn&apos;t on it yet.
                </p>
                <div className="flex flex-wrap gap-2">
                  {EXAMPLES.map((example) => (
                    <button
                      key={example}
                      type="button"
                      onClick={() => {
                        setQuestion(example)
                        inputRef.current?.focus()
                      }}
                      className="rounded-lg border border-slate-400 px-2.5 py-1 text-xs text-slate-600 transition hover:bg-slate-100 dark:border-slate-700 dark:text-slate-400 dark:hover:bg-slate-800"
                    >
                      {example}
                    </button>
                  ))}
                </div>
              </>
            )}

            {turns.map((turn, i) => (
              <div key={i}>
                <p className="text-xs font-medium text-slate-500 dark:text-slate-400">
                  {turn.role === 'user' ? 'You' : 'Assistant'}
                </p>
                <p className="mt-0.5 whitespace-pre-wrap text-sm text-slate-800 dark:text-slate-200">
                  {turn.content}
                </p>

                {turn.sources?.length > 0 && (
                  <p className="mt-1 text-xs text-slate-500">
                    From: {turn.sources.map((s) => (s.year ? `${s.title} (${s.year})` : s.title)).join(', ')}
                  </p>
                )}
              </div>
            ))}

            {busy && <p className="text-sm text-slate-500">Thinking…</p>}

            {unavailable && <p className="text-xs text-slate-500">{unavailable}</p>}

            {error && (
              <p className="rounded-lg bg-rose-500/10 px-3 py-2 text-sm text-rose-700 ring-1 ring-rose-500/30 dark:text-rose-300">
                {error}
              </p>
            )}
          </div>

          <form onSubmit={ask} className="flex gap-2 border-t border-slate-200 p-3 dark:border-slate-800">
            <label htmlFor="assistant-question" className="sr-only">
              Ask a question about your watchlist
            </label>
            <input
              ref={inputRef}
              id="assistant-question"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              disabled={busy}
              placeholder="Ask anything…"
              className="flex-1 rounded-lg border border-slate-400 bg-white px-3 py-2 text-sm outline-none placeholder-slate-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-950 dark:placeholder-slate-600"
            />
            <button
              type="submit"
              disabled={busy || !question.trim()}
              className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-500 disabled:opacity-50"
            >
              {busy ? '…' : 'Ask'}
            </button>
          </form>
        </div>
      )}

      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-label={open ? 'Close assistant' : 'Ask your watchlist'}
        aria-expanded={open}
        className="fixed bottom-4 right-4 z-50 flex h-12 w-12 items-center justify-center rounded-full bg-indigo-600 text-white shadow-lg transition hover:bg-indigo-500"
      >
        <svg viewBox="0 0 20 20" className="h-5 w-5" fill="currentColor" aria-hidden="true">
          <path d="M10 2c-4.42 0-8 2.91-8 6.5 0 1.98 1.09 3.75 2.81 4.95-.11.86-.46 1.99-1.4 2.99-.16.17-.05.45.19.44 1.6-.09 3.09-.72 4.11-1.4.73.16 1.5.02 2.29.02 4.42 0 8-2.91 8-6.5S14.42 2 10 2Z" />
        </svg>
      </button>
    </>
  )
}
