import { useEffect, useRef, useState } from 'react'
import { endChat, getChatHistory, getPublicInfo, sendChat } from '../services/api.js'
import { formatTime } from '../utils/format.js'
import './chatbox.css'

const SESSION_KEY = 'ava_chat_session'
const QUICK_REPLIES = ['Book an appointment', 'Opening hours', 'What services do you offer?', 'Talk to a person']

const now = () => new Date().toISOString()

function welcome(businessName) {
  return {
    from: 'ava',
    at: now(),
    text:
      `Hi, I'm Ava, the virtual receptionist${businessName ? ` of ${businessName}` : ''}. ` +
      'I can answer questions, book, reschedule or cancel appointments, or connect you with our team. How can I help?',
  }
}

export default function Chatbox() {
  const [open, setOpen] = useState(false)
  const [info, setInfo] = useState(null)
  const [messages, setMessages] = useState([welcome()])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [sessionId, setSessionId] = useState(() => localStorage.getItem(SESSION_KEY))
  const endRef = useRef(null)
  const inputRef = useRef(null)
  const restored = useRef(false)

  useEffect(() => {
    getPublicInfo()
      .then((data) => {
        setInfo(data)
        setMessages((prev) => (prev.length === 1 && prev[0].from === 'ava' ? [welcome(data.business_name)] : prev))
      })
      .catch(() => {})
  }, [])

  // Restore an existing conversation the first time the widget opens.
  useEffect(() => {
    if (!open || restored.current || !sessionId) return
    restored.current = true
    getChatHistory(sessionId)
      .then((data) => {
        if (data.messages?.length) {
          setMessages([
            welcome(info?.business_name),
            ...data.messages.map((m) => ({ from: m.from === 'user' ? 'user' : 'ava', text: m.text, at: m.created_at })),
          ])
        }
      })
      .catch(() => {
        localStorage.removeItem(SESSION_KEY)
        setSessionId(null)
      })
  }, [open, sessionId, info])

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, open, sending])

  useEffect(() => {
    if (open && !sending) inputRef.current?.focus()
  }, [open, sending])

  async function send(payload, displayText) {
    if (sending) return
    if (displayText) setMessages((prev) => [...prev, { from: 'user', text: displayText, at: now() }])
    setSending(true)
    try {
      const data = await sendChat({ ...payload, ...(sessionId && { session_id: sessionId }) })
      if (data.session_id && data.session_id !== sessionId) {
        setSessionId(data.session_id)
        localStorage.setItem(SESSION_KEY, data.session_id)
      }
      setMessages((prev) => [
        ...prev,
        { from: 'ava', text: data.reply, at: now(), ui_action: data.ui_action || null, data: data.data || null },
      ])
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        { from: 'ava', error: true, at: now(), text: error.message || 'Sorry, something went wrong. Please try again.' },
      ])
    } finally {
      setSending(false)
    }
  }

  function handleSend(e) {
    e.preventDefault()
    const text = input.trim()
    if (!text || sending) return
    setInput('')
    send({ message: text }, text)
  }

  function pickDate(item) {
    send({ message: '', action: 'select_date', selected_date: item.date }, `${item.day}, ${item.label}`)
  }

  function pickTime(date, slot) {
    send({ message: '', action: 'select_time', selected_date: date, selected_time: slot.time }, slot.label)
  }

  /* async function newChat() {
    if (sessionId) endChat(sessionId).catch(() => {})
    localStorage.removeItem(SESSION_KEY)
    setSessionId(null)
    setMessages([welcome(info?.business_name)])
    setInput('')
  } */

  const lastIndex = messages.length - 1
  const showQuickReplies = messages.length === 1 && !sending

  return (
    <div className="ava-chat">
      {open && (
        <div className="ava-chat-window card border-0 shadow-lg" role="dialog" aria-label="Chat with Ava">
          <div className="card-header bg-primary text-white d-flex align-items-center gap-2">
            <div className="ava-avatar">
              <i className="bi bi-robot"></i>
            </div>
            <div className="flex-grow-1 lh-sm">
              <div className="fw-semibold">Ava</div>
              <small className="text-white-50">
                AI Receptionist{info?.business_name ? ` · ${info.business_name}` : ''}
              </small>
            </div>
           
           {/*  <button type="button" className="btn btn-sm btn-outline-light" onClick={newChat} title="Start a new chat">
              <i className="bi bi-plus-lg"></i> New chat
            </button>
             */}
            <button type="button" className="btn-close btn-close-white ms-1" aria-label="Close chat"
                    onClick={() => setOpen(false)}></button>
          </div>

          <div className="card-body ava-chat-body" aria-live="polite">
            {messages.map((m, i) => (
              <div key={i} className={`d-flex flex-column mb-3 ${m.from === 'user' ? 'align-items-end' : 'align-items-start'}`}>
                <div className={`ava-bubble ${m.from === 'user' ? 'ava-bubble-user' : m.error ? 'ava-bubble-error' : 'ava-bubble-ava'}`}>
                  {m.error && <i className="bi bi-exclamation-circle me-1"></i>}
                  {m.text}
                </div>
                <small className="ava-time">{formatTime(m.at)}</small>

                {i === lastIndex && m.ui_action === 'select_date' && m.data?.dates && (
                  <div className="ava-options">
                    {m.data.dates.map((item) => (
                      <button key={item.date} type="button" disabled={sending || item.disabled}
                              onClick={() => pickDate(item)}
                              className={`btn btn-sm ${item.disabled ? 'btn-outline-secondary' : 'btn-outline-primary'}`}>
                        <div className="fw-semibold">{item.label}</div>
                        <small>{!item.is_open ? 'Closed' : item.disabled ? 'Full' : item.day}</small>
                      </button>
                    ))}
                  </div>
                )}

                {i === lastIndex && m.ui_action === 'select_time' && m.data?.slots && (
                  <div className="ava-options">
                    {m.data.slots.map((slot) => (
                      <button key={slot.time} type="button" disabled={sending || !slot.available}
                              onClick={() => pickTime(m.data.date, slot)}
                              className={`btn btn-sm ${slot.available ? 'btn-outline-primary' : 'btn-outline-secondary'}`}>
                        {slot.label}
                        {!slot.available && <small className="d-block">Booked</small>}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ))}

            {showQuickReplies && (
              <div className="ava-options mb-2">
                {QUICK_REPLIES.map((q) => (
                  <button key={q} type="button" className="btn btn-sm btn-light border" onClick={() => send({ message: q }, q)}>
                    {q}
                  </button>
                ))}
              </div>
            )}

            {sending && (
              <div className="d-flex mb-3">
                <div className="ava-bubble ava-bubble-ava ava-typing" aria-label="Ava is typing">
                  <span></span><span></span><span></span>
                </div>
              </div>
            )}
            <div ref={endRef}></div>
          </div>

          <div className="card-footer bg-white">
            <form className="input-group" onSubmit={handleSend}>
              <input ref={inputRef} className="form-control" placeholder="Type a message..." value={input}
                     maxLength={2000} onChange={(e) => setInput(e.target.value)} disabled={sending}
                     aria-label="Message" />
              <button className="btn btn-primary" type="submit" disabled={sending || !input.trim()} aria-label="Send">
                <i className="bi bi-send"></i>
              </button>
            </form>
            <div className="ava-disclaimer">Ava is an AI assistant. Bookings are confirmed by our team.</div>
          </div>
        </div>
      )}

      <div className="text-end">
        <button type="button" className="btn btn-primary rounded-circle shadow ava-toggle"
                aria-label={open ? 'Close chat' : 'Open chat'} onClick={() => setOpen(!open)}>
          <i className={`bi ${open ? 'bi-x-lg' : 'bi-chat-dots-fill'} fs-4`}></i>
        </button>
      </div>
    </div>
  )
}
