import { useCallback, useEffect, useRef, useState } from 'react'
import { getAvailability, getConversationMessages } from '../../services/api.js'
import { getAdmin } from '../../services/auth.js'
import { formatDateTime } from '../../utils/format.js'
import { ErrorAlert, Loading, Empty } from './ui.jsx'

export const isAdminRole = () => getAdmin()?.role === 'admin'

// Loads data with `fn` (re-runs whenever `deps` change). Returns {data, loading, error, reload, setError}.
export function useLoader(fn, deps = [], initial = null) {
  const [data, setData] = useState(initial)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const seq = useRef(0)

  const reload = useCallback(async () => {
    const id = ++seq.current
    setLoading(true)
    setError('')
    try {
      const result = await fn()
      if (id === seq.current) setData(result)
    } catch (err) {
      if (id === seq.current) setError(err.message)
    } finally {
      if (id === seq.current) setLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  useEffect(() => {
    reload()
  }, [reload])

  return { data, loading, error, reload, setError }
}

// Returns `value` after it stopped changing for `delay` ms (for search boxes).
export function useDebounced(value, delay = 350) {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(t)
  }, [value, delay])
  return debounced
}

// Brief success message that hides itself after a few seconds.
export function useFlash(timeout = 3500) {
  const [message, setMessage] = useState('')
  useEffect(() => {
    if (!message) return undefined
    const t = setTimeout(() => setMessage(''), timeout)
    return () => clearTimeout(t)
  }, [message, timeout])
  return [message, setMessage]
}

export function SuccessAlert({ message, onClose }) {
  if (!message) return null
  return (
    <div className="alert alert-success d-flex justify-content-between align-items-start py-2">
      <span>
        <i className="bi bi-check-circle me-2"></i>
        {message}
      </span>
      {onClose && <button type="button" className="btn-close" onClick={onClose}></button>}
    </div>
  )
}

// Runs an async mutation, reporting errors/success through the given setters.
export function useMutation(setError, setSuccess) {
  const [busy, setBusy] = useState(false)
  const run = useCallback(
    async (fn, successText, after) => {
      setBusy(true)
      setError('')
      try {
        const result = await fn()
        if (successText) setSuccess(successText)
        if (after) await after(result)
        return true
      } catch (err) {
        setError(err.message)
        return false
      } finally {
        setBusy(false)
      }
    },
    [setError, setSuccess]
  )
  return [run, busy]
}

export const todayISO = () => {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

// Loads free slots for `date` and lets the user pick one (value = "HH:MM").
export function SlotPicker({ date, value, onChange }) {
  const [slots, setSlots] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let alive = true
    onChange('')
    setSlots([])
    setError('')
    if (!date) return undefined
    setLoading(true)
    getAvailability(date)
      .then((res) => alive && setSlots(res.slots || []))
      .catch((err) => alive && setError(err.message))
      .finally(() => alive && setLoading(false))
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [date])

  if (!date) return <div className="form-text">Choose a date to see free time slots.</div>
  if (loading) return <div className="small text-muted"><span className="spinner-border spinner-border-sm me-2"></span>Loading slots...</div>
  if (error) return <ErrorAlert error={error} />
  const free = slots.filter((s) => s.available)
  if (!free.length) return <div className="small text-danger">No free slots on this date (closed, fully booked or outside the booking window).</div>
  return (
    <div className="d-flex flex-wrap gap-2">
      {slots.map((s) => (
        <button
          key={s.time}
          type="button"
          disabled={!s.available}
          className={`btn btn-sm ${value === s.time ? 'btn-primary' : 'btn-outline-primary'}`}
          onClick={() => onChange(s.time)}
        >
          {s.label}
        </button>
      ))}
    </div>
  )
}

// Chat-bubble transcript: user on the right, Ava on the left.
export function Transcript({ messages }) {
  if (!messages.length) return <Empty text="No messages in this conversation." />
  return (
    <div className="d-flex flex-column gap-2">
      {messages.map((m) => {
        const mine = m.sender === 'user'
        return (
          <div key={m.id} className={`d-flex ${mine ? 'justify-content-end' : 'justify-content-start'}`}>
            <div
              className={`px-3 py-2 rounded-3 ${mine ? 'bg-primary text-white' : 'bg-light border'}`}
              style={{ maxWidth: '80%', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}
            >
              <div className={`small fw-semibold mb-1 ${mine ? 'text-white-50' : 'text-muted'}`}>
                {mine ? 'Customer' : m.sender === 'ava' ? 'Ava' : m.sender}
              </div>
              {m.message}
              <div className={`mt-1 text-end ${mine ? 'text-white-50' : 'text-muted'}`} style={{ fontSize: '0.75rem' }}>
                {formatDateTime(m.created_at)}
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

// Fetches and shows the transcript of one conversation.
export function ConversationTranscript({ conversationId }) {
  const { data, loading, error } = useLoader(() => getConversationMessages(conversationId), [conversationId], [])
  if (loading) return <Loading />
  if (error) return <ErrorAlert error={error} />
  return <Transcript messages={data || []} />
}
