import { useState } from 'react'
import { deleteLead, getLeads, updateLead } from '../../services/api.js'
import { formatDateTime, label } from '../../utils/format.js'
import { Empty, ErrorAlert, Loading, Modal, PageHeader, RefreshButton } from '../../components/admin/ui.jsx'
import { SuccessAlert, isAdminRole, useDebounced, useFlash, useLoader, useMutation } from '../../components/admin/shared.jsx'

const STATUSES = ['new', 'contacted', 'qualified', 'converted', 'lost']

function NotesModal({ lead, onClose, onSave, busy, error }) {
  const [notes, setNotes] = useState(lead.notes || '')
  return (
    <Modal
      title={`Notes – ${lead.name || lead.phone || `Lead #${lead.id}`}`}
      onClose={onClose}
      footer={
        <>
          <button className="btn btn-outline-secondary" onClick={onClose}>Close</button>
          <button className="btn btn-primary" disabled={busy} onClick={() => onSave(notes)}>{busy ? 'Saving...' : 'Save notes'}</button>
        </>
      }
    >
      <ErrorAlert error={error} />
      {lead.message && (
        <div className="mb-3">
          <div className="small text-muted">Customer message</div>
          <div className="border rounded p-2 small bg-light" style={{ whiteSpace: 'pre-wrap' }}>{lead.message}</div>
        </div>
      )}
      <label className="form-label">Internal notes</label>
      <textarea className="form-control" rows={5} maxLength={2000} value={notes} onChange={(e) => setNotes(e.target.value)}></textarea>
    </Modal>
  )
}

export default function Leads() {
  const [status, setStatus] = useState('')
  const [q, setQ] = useState('')
  const query = useDebounced(q)
  const { data, loading, error, reload, setError } = useLoader(() => getLeads({ status, q: query.trim() }), [status, query], [])
  const [success, setSuccess] = useFlash()
  const [run, busy] = useMutation(setError, setSuccess)
  const [editing, setEditing] = useState(null)
  const isAdmin = isAdminRole()
  const rows = data || []

  const changeStatus = (lead, value) => run(() => updateLead(lead.id, { status: value }), `Lead status changed to ${value}.`, reload)
  const saveNotes = async (notes) => {
    const ok = await run(() => updateLead(editing.id, { notes }), 'Notes saved.', reload)
    if (ok) setEditing(null)
  }
  const remove = (lead) => {
    if (!window.confirm(`Delete the lead of ${lead.name || lead.phone || `#${lead.id}`}? This cannot be undone.`)) return
    run(() => deleteLead(lead.id), 'Lead deleted.', reload)
  }

  return (
    <>
      <PageHeader title="Leads" icon="bi-funnel">
        <select className="form-select form-select-sm" style={{ width: 150 }} value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All statuses</option>
          {STATUSES.map((s) => <option key={s} value={s}>{label(s)}</option>)}
        </select>
        <input className="form-control form-control-sm" style={{ maxWidth: 220 }} placeholder="Search" value={q} onChange={(e) => setQ(e.target.value)} />
        <RefreshButton onClick={reload} loading={loading} />
      </PageHeader>
      <ErrorAlert error={error} onClose={() => setError('')} />
      <SuccessAlert message={success} onClose={() => setSuccess('')} />

      <div className="card border-0 shadow-sm">
        {loading && !rows.length ? <Loading /> : !rows.length ? <Empty text="No leads found." /> : (
          <div className="table-responsive">
            <table className="table table-hover align-middle mb-0 small">
              <thead className="table-light">
                <tr>
                  <th>Name</th><th>Contact</th><th>Service</th><th>Preferred time</th><th>Message</th><th>Source</th><th>Status</th><th>Created</th><th className="text-end">Actions</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((lead) => (
                  <tr key={lead.id}>
                    <td className="fw-semibold">{lead.name || '-'}</td>
                    <td className="text-nowrap">{lead.phone || '-'}{lead.email && <div className="text-muted">{lead.email}</div>}</td>
                    <td>{lead.requested_service || '-'}</td>
                    <td>{lead.preferred_datetime || '-'}</td>
                    <td style={{ minWidth: 180, maxWidth: 280 }}>
                      <div className="text-truncate" title={lead.message || ''}>{lead.message || '-'}</div>
                      {lead.notes && <div className="text-muted text-truncate" title={lead.notes}><i className="bi bi-sticky me-1"></i>{lead.notes}</div>}
                    </td>
                    <td className="text-capitalize">{label(lead.source)}</td>
                    <td>
                      <select className="form-select form-select-sm" style={{ width: 125 }} value={lead.status} disabled={busy}
                        onChange={(e) => changeStatus(lead, e.target.value)} aria-label="Lead status">
                        {STATUSES.map((s) => <option key={s} value={s}>{label(s)}</option>)}
                      </select>
                    </td>
                    <td className="text-nowrap text-muted">{formatDateTime(lead.created_at)}</td>
                    <td className="text-end text-nowrap">
                      <button className="btn btn-sm btn-outline-secondary me-1" title="Notes" onClick={() => setEditing(lead)}>
                        <i className="bi bi-pencil-square"></i>
                      </button>
                      {isAdmin && (
                        <button className="btn btn-sm btn-outline-danger" title="Delete" disabled={busy} onClick={() => remove(lead)}>
                          <i className="bi bi-trash"></i>
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      {editing && <NotesModal lead={editing} busy={busy} error={error} onClose={() => setEditing(null)} onSave={saveNotes} />}
    </>
  )
}
