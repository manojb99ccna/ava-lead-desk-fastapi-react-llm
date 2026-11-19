import { useState } from 'react'
import { getConversations } from '../../services/api.js'
import { formatDateTime, label } from '../../utils/format.js'
import { Empty, ErrorAlert, Loading, PageHeader, RefreshButton, StatusBadge } from '../../components/admin/ui.jsx'
import { ConversationTranscript, useLoader } from '../../components/admin/shared.jsx'

const STATUSES = ['active', 'handoff', 'closed']

export default function Conversations() {
  const [status, setStatus] = useState('')
  const [selected, setSelected] = useState(null)
  const { data, loading, error, reload, setError } = useLoader(() => getConversations({ status }), [status], [])
  const rows = data || []

  return (
    <>
      <PageHeader title="Conversations" icon="bi-chat-dots">
        <select className="form-select form-select-sm" style={{ width: 150 }} value={status}
                onChange={(e) => { setStatus(e.target.value); setSelected(null) }}>
          <option value="">All statuses</option>
          {STATUSES.map((s) => <option key={s} value={s}>{label(s)}</option>)}
        </select>
        <RefreshButton onClick={reload} loading={loading} />
      </PageHeader>
      <ErrorAlert error={error} onClose={() => setError('')} />

      <div className="row g-3">
        <div className={`col-lg-5 ${selected ? 'd-none d-lg-block' : ''}`}>
          <div className="card border-0 shadow-sm">
            {loading && !rows.length ? <Loading /> : !rows.length ? <Empty text="No conversations yet." /> : (
              <div className="list-group list-group-flush" style={{ maxHeight: '70vh', overflowY: 'auto' }}>
                {rows.map((c) => (
                  <button key={c.id} type="button" onClick={() => setSelected(c)}
                          className={`list-group-item list-group-item-action ${selected?.id === c.id ? 'active' : ''}`}>
                    <div className="d-flex justify-content-between align-items-center gap-2">
                      <span className="fw-semibold">#{c.id}</span>
                      <span className="d-flex gap-1">
                        <StatusBadge value={c.status} />
                        {c.engine && <StatusBadge value={c.engine} />}
                        <span className="badge text-bg-light border text-capitalize">{c.channel || 'web'}</span>
                      </span>
                    </div>
                    <div className={`small ${selected?.id === c.id ? 'text-white-50' : 'text-muted'}`}>
                      {c.message_count} messages · {formatDateTime(c.updated_at)}
                      {c.intent && <> · {label(c.intent)}</>}
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className={`col-lg-7 ${selected ? '' : 'd-none d-lg-block'}`}>
          <div className="card border-0 shadow-sm">
            <div className="card-header bg-white d-flex align-items-center gap-2">
              {selected && (
                <button className="btn btn-sm btn-outline-secondary d-lg-none" onClick={() => setSelected(null)}>
                  <i className="bi bi-arrow-left"></i>
                </button>
              )}
              <span className="fw-semibold">{selected ? `Conversation #${selected.id}` : 'Transcript'}</span>
              {selected?.current_step && <span className="small text-muted">step: {label(selected.current_step)}</span>}
            </div>
            <div className="card-body" style={{ maxHeight: '70vh', overflowY: 'auto' }}>
              {selected ? <ConversationTranscript conversationId={selected.id} /> : <Empty text="Select a conversation." />}
            </div>
          </div>
        </div>
      </div>
    </>
  )
}
