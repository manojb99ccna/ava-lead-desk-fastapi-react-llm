import { useState } from 'react'
import { createFaq, deleteFaq, getFaqs, searchFaqs, updateFaq } from '../../services/api.js'
import { formatDateTime, label } from '../../utils/format.js'
import { Empty, ErrorAlert, Loading, Modal, PageHeader, RefreshButton } from '../../components/admin/ui.jsx'
import { SuccessAlert, isAdminRole, useFlash, useLoader, useMutation } from '../../components/admin/shared.jsx'

const EMPTY = { intent: '', question: '', answer: '', is_active: true }

function FaqForm({ initial, onClose, onSave, busy, error }) {
  const [form, setForm] = useState(initial)
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })
  return (
    <Modal title={initial.id ? 'Edit FAQ' : 'New FAQ'} onClose={onClose} size="modal-lg"
           footer={<>
             <button className="btn btn-outline-secondary" onClick={onClose}>Cancel</button>
             <button className="btn btn-primary" disabled={busy} onClick={() => onSave(form)}>{busy ? 'Saving...' : 'Save'}</button>
           </>}>
      <ErrorAlert error={error} />
      <div className="mb-3">
        <label className="form-label">Topic / intent</label>
        <input className="form-control" value={form.intent} onChange={set('intent')} maxLength={50}
               placeholder="e.g. pricing, services, parking" />
        <div className="form-text">Letters, numbers, spaces, - and _ only.</div>
      </div>
      <div className="mb-3">
        <label className="form-label">Question</label>
        <input className="form-control" value={form.question} onChange={set('question')} maxLength={1000} />
      </div>
      <div className="mb-3">
        <label className="form-label">Answer</label>
        <textarea className="form-control" rows={5} value={form.answer} onChange={set('answer')} maxLength={5000}></textarea>
      </div>
      <div className="form-check">
        <input className="form-check-input" type="checkbox" id="faq-active" checked={form.is_active} onChange={set('is_active')} />
        <label className="form-check-label" htmlFor="faq-active">Active (Ava may use this answer)</label>
      </div>
    </Modal>
  )
}

function TestBox() {
  const [q, setQ] = useState('')
  const [results, setResults] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function run(e) {
    e.preventDefault()
    if (q.trim().length < 2) return
    setBusy(true)
    setError('')
    try {
      setResults(await searchFaqs(q.trim()))
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="card border-0 shadow-sm mb-4">
      <div className="card-body">
        <h6 className="mb-2"><i className="bi bi-search me-2"></i>Test a question</h6>
        <p className="small text-muted mb-2">See which FAQ Ava would match. Spelling mistakes are tolerated.</p>
        <form className="input-group mb-2" onSubmit={run}>
          <input className="form-control" value={q} onChange={(e) => setQ(e.target.value)} placeholder="e.g. how much does a websit cost" />
          <button className="btn btn-outline-primary" disabled={busy}>Test</button>
        </form>
        <ErrorAlert error={error} />
        {results && (results.length ? (
          <ul className="list-group small">
            {results.map((r) => (
              <li key={r.id} className="list-group-item d-flex justify-content-between gap-2">
                <span><span className="fw-semibold">{r.question}</span><br /><span className="text-muted">{r.answer}</span></span>
                <span className="text-nowrap">
                  <span className="badge text-bg-light border me-1">{r.score.toFixed(2)}</span>
                  {r.confident ? <span className="badge text-bg-success">match</span> : <span className="badge text-bg-secondary">weak</span>}
                </span>
              </li>
            ))}
          </ul>
        ) : <div className="small text-muted">No active FAQs.</div>)}
      </div>
    </div>
  )
}

export default function Faqs() {
  const { data, loading, error, reload, setError } = useLoader(getFaqs, [], [])
  const [success, setSuccess] = useFlash()
  const [run, busy] = useMutation(setError, setSuccess)
  const [editing, setEditing] = useState(null)
  const isAdmin = isAdminRole()
  const rows = data || []

  async function save(form) {
    const payload = { intent: form.intent.trim(), question: form.question.trim(), answer: form.answer.trim(), is_active: form.is_active }
    const ok = await run(() => (form.id ? updateFaq(form.id, payload) : createFaq(payload)), 'FAQ saved.', reload)
    if (ok) setEditing(null)
  }

  function remove(faq) {
    if (!window.confirm(`Delete the FAQ "${faq.question}"?`)) return
    run(() => deleteFaq(faq.id), 'FAQ deleted.', reload)
  }

  return (
    <>
      <PageHeader title="Business FAQs" icon="bi-question-circle">
        <RefreshButton onClick={reload} loading={loading} />
        {isAdmin && (
          <button className="btn btn-primary btn-sm" onClick={() => setEditing(EMPTY)}>
            <i className="bi bi-plus-lg me-1"></i>New FAQ
          </button>
        )}
      </PageHeader>
      {!isAdmin && <div className="alert alert-info py-2 small">You can view FAQs. Only admins can change them.</div>}
      <ErrorAlert error={error} onClose={() => setError('')} />
      <SuccessAlert message={success} onClose={() => setSuccess('')} />
      <TestBox />

      <div className="card border-0 shadow-sm">
        {loading && !rows.length ? <Loading /> : !rows.length ? <Empty text="No FAQs yet." /> : (
          <div className="table-responsive">
            <table className="table table-hover align-middle mb-0 small">
              <thead className="table-light">
                <tr><th>Topic</th><th>Question</th><th>Answer</th><th>Active</th><th>Updated</th>{isAdmin && <th className="text-end">Actions</th>}</tr>
              </thead>
              <tbody>
                {rows.map((f) => (
                  <tr key={f.id} className={f.is_active ? '' : 'text-muted'}>
                    <td className="text-capitalize text-nowrap">{label(f.intent)}</td>
                    <td style={{ minWidth: 200 }}>{f.question}</td>
                    <td style={{ minWidth: 240, maxWidth: 420 }}><div className="text-truncate" title={f.answer}>{f.answer}</div></td>
                    <td>{f.is_active ? <i className="bi bi-check-circle-fill text-success"></i> : <i className="bi bi-x-circle text-secondary"></i>}</td>
                    <td className="text-nowrap">{formatDateTime(f.updated_at)}</td>
                    {isAdmin && (
                      <td className="text-end text-nowrap">
                        <button className="btn btn-sm btn-outline-secondary me-1" title="Edit" onClick={() => setEditing(f)}><i className="bi bi-pencil"></i></button>
                        <button className="btn btn-sm btn-outline-danger" title="Delete" disabled={busy} onClick={() => remove(f)}><i className="bi bi-trash"></i></button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      {editing && <FaqForm initial={editing} busy={busy} error={error} onClose={() => setEditing(null)} onSave={save} />}
    </>
  )
}
