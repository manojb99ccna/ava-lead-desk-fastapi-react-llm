import { useState } from 'react'
import { getCustomer, getCustomers } from '../../services/api.js'
import { formatDateTime } from '../../utils/format.js'
import { Empty, ErrorAlert, Loading, Modal, PageHeader, RefreshButton, StatusBadge } from '../../components/admin/ui.jsx'
import { ConversationTranscript, useDebounced, useLoader } from '../../components/admin/shared.jsx'

function Section({ title, icon, count, children }) {
  return (
    <div className="mb-4">
      <h6 className="mb-2"><i className={`bi ${icon} me-2 text-primary`}></i>{title} <span className="badge text-bg-light">{count}</span></h6>
      {count ? children : <div className="small text-muted">None.</div>}
    </div>
  )
}

function CustomerModal({ id, onClose }) {
  const { data, loading, error } = useLoader(() => getCustomer(id), [id])
  const [conversation, setConversation] = useState(null)
  const c = data?.customer

  return (
    <Modal title={c ? c.name || c.phone || `Customer #${c.id}` : 'Customer'} onClose={onClose} size="modal-lg">
      <ErrorAlert error={error} />
      {loading ? <Loading /> : data && (
        conversation ? (
          <>
            <button className="btn btn-sm btn-outline-secondary mb-3" onClick={() => setConversation(null)}>
              <i className="bi bi-arrow-left me-1"></i>Back to customer
            </button>
            <ConversationTranscript conversationId={conversation} />
          </>
        ) : (
          <>
            <p className="small text-muted">
              <i className="bi bi-telephone me-1"></i>{c.phone || '-'} · <i className="bi bi-envelope me-1"></i>{c.email || '-'} · since {formatDateTime(c.created_at)}
            </p>
            <Section title="Appointments" icon="bi-calendar-check" count={data.appointments.length}>
              <div className="table-responsive">
                <table className="table table-sm small align-middle">
                  <thead><tr><th>Code</th><th>Service</th><th>When</th><th>Status</th></tr></thead>
                  <tbody>
                    {data.appointments.map((a) => (
                      <tr key={a.id}>
                        <td><code>{a.booking_code}</code></td><td>{a.service}</td>
                        <td className="text-nowrap">{formatDateTime(a.appointment_date)}</td><td><StatusBadge value={a.status} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Section>
            <Section title="Leads" icon="bi-funnel" count={data.leads.length}>
              <ul className="list-group small">
                {data.leads.map((l) => (
                  <li key={l.id} className="list-group-item d-flex justify-content-between gap-2">
                    <span>{l.requested_service || 'General enquiry'} <span className="text-muted">· {formatDateTime(l.created_at)}</span></span>
                    <StatusBadge value={l.status} />
                  </li>
                ))}
              </ul>
            </Section>
            <Section title="Conversations" icon="bi-chat-dots" count={data.conversations.length}>
              <ul className="list-group small">
                {data.conversations.map((cv) => (
                  <li key={cv.id} className="list-group-item list-group-item-action d-flex justify-content-between gap-2" role="button" onClick={() => setConversation(cv.id)}>
                    <span>Conversation #{cv.id} <span className="text-muted">· {formatDateTime(cv.updated_at)}</span></span>
                    <StatusBadge value={cv.status} />
                  </li>
                ))}
              </ul>
            </Section>
          </>
        )
      )}
    </Modal>
  )
}

export default function Customers() {
  const [q, setQ] = useState('')
  const query = useDebounced(q)
  const { data, loading, error, reload } = useLoader(() => getCustomers(query.trim()), [query], [])
  const [selected, setSelected] = useState(null)
  const rows = data || []

  return (
    <>
      <PageHeader title="Customers" icon="bi-people">
        <input className="form-control form-control-sm" style={{ maxWidth: 240 }} placeholder="Search name, phone, e-mail" value={q} onChange={(e) => setQ(e.target.value)} />
        <RefreshButton onClick={reload} loading={loading} />
      </PageHeader>
      <ErrorAlert error={error} />
      <div className="card border-0 shadow-sm">
        {loading && !rows.length ? <Loading /> : !rows.length ? <Empty text="No customers found." /> : (
          <div className="table-responsive">
            <table className="table table-hover align-middle mb-0 small">
              <thead className="table-light">
                <tr><th>Name</th><th>Phone</th><th>E-mail</th><th className="text-center">Appointments</th><th className="text-center">Leads</th><th>Updated</th></tr>
              </thead>
              <tbody>
                {rows.map((c) => (
                  <tr key={c.id} role="button" onClick={() => setSelected(c.id)}>
                    <td className="fw-semibold">{c.name || '-'}</td>
                    <td className="text-nowrap">{c.phone || '-'}</td>
                    <td>{c.email || '-'}</td>
                    <td className="text-center">{c.appointments}</td>
                    <td className="text-center">{c.leads}</td>
                    <td className="text-nowrap text-muted">{formatDateTime(c.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      {selected && <CustomerModal id={selected} onClose={() => setSelected(null)} />}
    </>
  )
}
