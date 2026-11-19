import { useState } from 'react'
import { getHandoffs, updateHandoff } from '../../services/api.js'
import { formatDateTime, label } from '../../utils/format.js'
import { Empty, ErrorAlert, Loading, Modal, PageHeader, RefreshButton, StatusBadge } from '../../components/admin/ui.jsx'
import { ConversationTranscript, SuccessAlert, useFlash, useLoader, useMutation } from '../../components/admin/shared.jsx'

const STATUSES = ['open', 'in_progress', 'resolved']

function ResolveModal({ handoff, onClose, onSave, busy, error }) {
  const [note, setNote] = useState(handoff.resolution_note || '')
  return (
    <Modal title={`Resolve request #${handoff.id}`} onClose={onClose}
           footer={<>
             <button className="btn btn-outline-secondary" onClick={onClose}>Cancel</button>
             <button className="btn btn-success" disabled={busy} onClick={() => onSave(note)}>{busy ? 'Saving...' : 'Mark resolved'}</button>
           </>}>
      <ErrorAlert error={error} />
      <label className="form-label">What was done? (internal note)</label>
      <textarea className="form-control" rows={4} maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)}
                placeholder="e.g. Called the customer, booked a meeting for Friday."></textarea>
    </Modal>
  )
}

export default function Handoffs() {
  const [status, setStatus] = useState('open')
  const { data, loading, error, reload, setError } = useLoader(() => getHandoffs(status), [status], [])
  const [success, setSuccess] = useFlash()
  const [run, busy] = useMutation(setError, setSuccess)
  const [resolving, setResolving] = useState(null)
  const [viewing, setViewing] = useState(null)
  const rows = data || []

  const take = (h) => run(() => updateHandoff(h.id, { assign_to_me: true, status: 'in_progress' }), 'Request assigned to you.', reload)
  const reopen = (h) => run(() => updateHandoff(h.id, { status: 'open' }), 'Request reopened.', reload)
  const resolve = async (note) => {
    const ok = await run(() => updateHandoff(resolving.id, { status: 'resolved', resolution_note: note }), 'Request resolved.', reload)
    if (ok) setResolving(null)
  }

  return (
    <>
      <PageHeader title="Human handoff requests" icon="bi-person-raised-hand">
        <select className="form-select form-select-sm" style={{ width: 160 }} value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All statuses</option>
          {STATUSES.map((s) => <option key={s} value={s}>{label(s)}</option>)}
        </select>
        <RefreshButton onClick={reload} loading={loading} />
      </PageHeader>
      <p className="small text-muted">
        Customers who asked for a person, complained, or followed up on an earlier request. Ava has told them a team
        member will contact them, so please reply.
      </p>
      <ErrorAlert error={error} onClose={() => setError('')} />
      <SuccessAlert message={success} onClose={() => setSuccess('')} />

      <div className="card border-0 shadow-sm">
        {loading && !rows.length ? <Loading /> : !rows.length ? <Empty text="No requests with this status." /> : (
          <div className="table-responsive">
            <table className="table table-hover align-middle mb-0 small">
              <thead className="table-light">
                <tr><th>#</th><th>Customer</th><th>Reason</th><th>Status</th><th>Assigned</th><th>Created</th><th className="text-end">Actions</th></tr>
              </thead>
              <tbody>
                {rows.map((h) => (
                  <tr key={h.id}>
                    <td>{h.id}</td>
                    <td className="text-nowrap">
                      <div className="fw-semibold">{h.name || 'Unknown'}</div>
                      <div className="text-muted">{h.phone || h.email || 'no contact details yet'}</div>
                    </td>
                    <td style={{ minWidth: 220, maxWidth: 380 }}>
                      <div className="text-truncate" title={h.reason || ''}>{h.reason || '-'}</div>
                      {h.resolution_note && <div className="text-success text-truncate" title={h.resolution_note}><i className="bi bi-check2 me-1"></i>{h.resolution_note}</div>}
                    </td>
                    <td><StatusBadge value={h.status} /></td>
                    <td>{h.assigned_to || '-'}</td>
                    <td className="text-nowrap">{formatDateTime(h.created_at)}</td>
                    <td className="text-end text-nowrap">
                      <button className="btn btn-sm btn-outline-secondary me-1" title="View conversation" onClick={() => setViewing(h)}>
                        <i className="bi bi-chat-text"></i>
                      </button>
                      {h.status === 'open' && (
                        <button className="btn btn-sm btn-outline-primary me-1" disabled={busy} onClick={() => take(h)}>Assign to me</button>
                      )}
                      {h.status !== 'resolved' ? (
                        <button className="btn btn-sm btn-success" disabled={busy} onClick={() => setResolving(h)}>Resolve</button>
                      ) : (
                        <button className="btn btn-sm btn-outline-secondary" disabled={busy} onClick={() => reopen(h)}>Reopen</button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {resolving && <ResolveModal handoff={resolving} busy={busy} error={error} onClose={() => setResolving(null)} onSave={resolve} />}
      {viewing && (
        <Modal title={`Conversation #${viewing.conversation_id}`} size="modal-lg" onClose={() => setViewing(null)}>
          <ConversationTranscript conversationId={viewing.conversation_id} />
        </Modal>
      )}
    </>
  )
}
