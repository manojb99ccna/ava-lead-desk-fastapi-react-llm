import { Link } from 'react-router-dom'
import { getDashboard } from '../../services/api.js'
import { formatDateTime } from '../../utils/format.js'
import { Empty, ErrorAlert, Loading, PageHeader, RefreshButton, StatusBadge } from '../../components/admin/ui.jsx'
import { useLoader } from '../../components/admin/shared.jsx'

const CARDS = [
  { key: 'appointments_today', label: 'Appointments today', icon: 'bi-calendar-day', color: 'primary', to: '/admin/appointments' },
  { key: 'appointments_pending', label: 'Pending appointments', icon: 'bi-hourglass-split', color: 'warning', to: '/admin/appointments' },
  { key: 'appointments_upcoming', label: 'Upcoming appointments', icon: 'bi-calendar-check', color: 'info', to: '/admin/appointments' },
  { key: 'handoffs_open', label: 'Open handoffs', icon: 'bi-person-raised-hand', color: 'danger', to: '/admin/handoffs' },
  { key: 'leads_new', label: 'New leads', icon: 'bi-funnel', color: 'success', to: '/admin/leads' },
  { key: 'customers_total', label: 'Customers', icon: 'bi-people', color: 'secondary', to: '/admin/customers' },
  { key: 'conversations_today', label: 'Conversations today', icon: 'bi-chat-dots', color: 'primary', to: '/admin/conversations' },
  { key: 'conversations_7d', label: 'Conversations (7 days)', icon: 'bi-chat-square-text', color: 'info', to: '/admin/conversations' },
  { key: 'messages_7d', label: 'Messages (7 days)', icon: 'bi-envelope', color: 'dark', to: '/admin/conversations' },
]

const LLM_BADGE = { ready: 'success', loading: 'warning', error: 'danger', disabled: 'secondary', idle: 'secondary' }

function StatCard({ card, value }) {
  return (
    <Link to={card.to} className="text-decoration-none">
      <div className="card border-0 shadow-sm h-100">
        <div className="card-body d-flex align-items-center gap-3">
          <div className={`rounded-3 bg-${card.color} bg-opacity-10 text-${card.color} d-flex align-items-center justify-content-center`} style={{ width: 48, height: 48 }}>
            <i className={`bi ${card.icon} fs-4`}></i>
          </div>
          <div>
            <div className="fs-4 fw-bold text-dark lh-1">{value ?? 0}</div>
            <div className="small text-muted">{card.label}</div>
          </div>
        </div>
      </div>
    </Link>
  )
}

function EngineCard({ byEngine }) {
  const entries = Object.entries(byEngine || {})
  const total = entries.reduce((sum, [, n]) => sum + n, 0)
  return (
    <div className="card border-0 shadow-sm h-100">
      <div className="card-header bg-white fw-semibold"><i className="bi bi-diagram-3 me-2"></i>Conversations by engine</div>
      <div className="card-body">
        {!entries.length ? (
          <Empty text="No conversations yet." />
        ) : (
          entries.map(([engine, n]) => (
            <div key={engine} className="mb-3">
              <div className="d-flex justify-content-between small mb-1">
                <span><StatusBadge value={engine} /></span>
                <span className="fw-semibold">{n}</span>
              </div>
              <div className="progress" style={{ height: 8 }}>
                <div className={`progress-bar ${engine === 'llm' ? 'bg-primary' : 'bg-secondary'}`} style={{ width: `${total ? (n / total) * 100 : 0}%` }}></div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}

function LlmCard({ llm }) {
  if (!llm) return null
  return (
    <div className="card border-0 shadow-sm h-100">
      <div className="card-header bg-white fw-semibold"><i className="bi bi-cpu me-2"></i>AI engine</div>
      <div className="card-body small">
        <dl className="row mb-0">
          <dt className="col-5">Status</dt>
          <dd className="col-7"><span className={`badge text-bg-${LLM_BADGE[llm.status] || 'light'} text-capitalize`}>{llm.status}</span></dd>
          <dt className="col-5">Provider</dt>
          <dd className="col-7">{llm.provider || '-'}</dd>
          <dt className="col-5">Model</dt>
          <dd className="col-7 text-break">{llm.model || '-'}</dd>
          {llm.device && (<><dt className="col-5">Device</dt><dd className="col-7">{llm.device}</dd></>)}
        </dl>
        {llm.error && <div className="alert alert-danger small mt-2 mb-0 text-break">{llm.error}</div>}
        {llm.status === 'disabled' && <div className="text-muted mt-2">The LLM is disabled; Ava answers with the rule-based engine.</div>}
      </div>
    </div>
  )
}

function UpcomingCard({ items }) {
  return (
    <div className="card border-0 shadow-sm h-100">
      <div className="card-header bg-white d-flex justify-content-between align-items-center">
        <span className="fw-semibold"><i className="bi bi-calendar-event me-2"></i>Upcoming appointments</span>
        <Link to="/admin/appointments" className="small">View all</Link>
      </div>
      {!items.length ? (
        <Empty text="No upcoming appointments." />
      ) : (
        <ul className="list-group list-group-flush">
          {items.map((a) => (
            <li key={a.id} className="list-group-item d-flex flex-wrap justify-content-between align-items-center gap-2">
              <div>
                <div className="fw-semibold">{a.name} <span className="text-muted small">· {a.service}</span></div>
                <div className="small text-muted">{formatDateTime(a.appointment_date)} · {a.phone} · <code>{a.booking_code}</code></div>
              </div>
              <StatusBadge value={a.status} />
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export default function Dashboard() {
  const { data, loading, error, reload } = useLoader(getDashboard, [])

  return (
    <>
      <PageHeader title="Dashboard" icon="bi-speedometer2">
        <RefreshButton onClick={reload} loading={loading} />
      </PageHeader>
      <ErrorAlert error={error} />
      {loading && !data ? (
        <Loading />
      ) : data ? (
        <>
          <div className="row g-3 mb-4">
            {CARDS.map((c) => (
              <div key={c.key} className="col-6 col-md-4 col-xl-4">
                <StatCard card={c} value={data.stats?.[c.key]} />
              </div>
            ))}
          </div>
          <div className="row g-3">
            <div className="col-lg-6"><UpcomingCard items={data.upcoming_appointments || []} /></div>
            <div className="col-md-6 col-lg-3"><EngineCard byEngine={data.conversations_by_engine} /></div>
            <div className="col-md-6 col-lg-3"><LlmCard llm={data.llm} /></div>
          </div>
        </>
      ) : null}
    </>
  )
}
