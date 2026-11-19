import { useEffect, useState } from 'react'
import {
  createService, deleteService, getBusinessHours, getBusinessSettings, getServices,
  updateBusinessHours, updateBusinessSettings, updateService,
} from '../../services/api.js'
import { ErrorAlert, Loading, Modal, PageHeader } from '../../components/admin/ui.jsx'
import { SuccessAlert, isAdminRole, useFlash, useLoader, useMutation } from '../../components/admin/shared.jsx'

const SETTINGS_FIELDS = [
  ['business_name', 'Business name', 'text'], ['phone', 'Phone', 'text'], ['email', 'E-mail', 'email'],
  ['website', 'Website', 'text'], ['address', 'Address', 'text'], ['timezone', 'Timezone (e.g. Asia/Kolkata)', 'text'],
]

function SettingsCard({ canEdit }) {
  const { data, loading, error, setError } = useLoader(getBusinessSettings, [])
  const [form, setForm] = useState(null)
  const [success, setSuccess] = useFlash()
  const [run, busy] = useMutation(setError, setSuccess)
  useEffect(() => { if (data) setForm(data) }, [data])
  if (loading || !form) return <div className="card border-0 shadow-sm mb-4"><Loading /></div>
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })

  function save(e) {
    e.preventDefault()
    const payload = {}
    for (const [k] of SETTINGS_FIELDS) payload[k] = (form[k] ?? '').toString().trim() || null
    payload.business_name = payload.business_name || ''
    payload.timezone = payload.timezone || 'Asia/Kolkata'
    payload.description = (form.description || '').trim() || null
    payload.appointment_duration_minutes = Number(form.appointment_duration_minutes)
    payload.booking_window_days = Number(form.booking_window_days)
    run(() => updateBusinessSettings(payload), 'Business information saved. Ava uses it immediately.', (res) => setForm(res))
  }

  return (
    <div className="card border-0 shadow-sm mb-4">
      <div className="card-body">
        <h5 className="mb-1">Business information</h5>
        <p className="small text-muted">Ava only tells customers facts from here, the services list, opening hours and the FAQs.</p>
        <ErrorAlert error={error} onClose={() => setError('')} />
        <SuccessAlert message={success} />
        <form onSubmit={save}>
          <fieldset disabled={!canEdit || busy}>
            <div className="row g-3">
              {SETTINGS_FIELDS.map(([k, text, type]) => (
                <div className="col-md-6" key={k}>
                  <label className="form-label">{text}</label>
                  <input type={type} className="form-control" value={form[k] ?? ''} onChange={set(k)} required={k === 'business_name'} />
                </div>
              ))}
              <div className="col-12">
                <label className="form-label">Description</label>
                <textarea className="form-control" rows={3} value={form.description ?? ''} onChange={set('description')} maxLength={5000}></textarea>
              </div>
              <div className="col-sm-6">
                <label className="form-label">Appointment length (minutes)</label>
                <input type="number" min={5} max={480} className="form-control" value={form.appointment_duration_minutes} onChange={set('appointment_duration_minutes')} />
              </div>
              <div className="col-sm-6">
                <label className="form-label">Booking window (days ahead)</label>
                <input type="number" min={1} max={365} className="form-control" value={form.booking_window_days} onChange={set('booking_window_days')} />
              </div>
            </div>
            {canEdit && <button className="btn btn-primary mt-3">Save information</button>}
          </fieldset>
        </form>
      </div>
    </div>
  )
}

function HoursCard({ canEdit }) {
  const { data, loading, error, setError } = useLoader(getBusinessHours, [])
  const [days, setDays] = useState(null)
  const [success, setSuccess] = useFlash()
  const [run, busy] = useMutation(setError, setSuccess)
  useEffect(() => {
    if (data) setDays(data.map((d) => ({ ...d, opening_time: d.opening_time || '09:00', closing_time: d.closing_time || '18:00' })))
  }, [data])
  if (loading || !days) return <div className="card border-0 shadow-sm mb-4"><Loading /></div>
  const update = (i, patch) => setDays(days.map((d, j) => (j === i ? { ...d, ...patch } : d)))

  function save() {
    const payload = days.map((d) => ({
      day_of_week: d.day_of_week, is_open: d.is_open,
      opening_time: d.is_open ? d.opening_time : null, closing_time: d.is_open ? d.closing_time : null,
    }))
    run(() => updateBusinessHours(payload), 'Opening hours saved.')
  }

  return (
    <div className="card border-0 shadow-sm mb-4">
      <div className="card-body">
        <h5 className="mb-1">Opening hours</h5>
        <p className="small text-muted">Appointment slots are generated from these hours.</p>
        <ErrorAlert error={error} onClose={() => setError('')} />
        <SuccessAlert message={success} />
        <div className="table-responsive">
          <table className="table align-middle small mb-0">
            <tbody>
              {days.map((d, i) => (
                <tr key={d.day_of_week}>
                  <td className="fw-semibold" style={{ width: 120 }}>{d.day}</td>
                  <td style={{ width: 110 }}>
                    <div className="form-check form-switch mb-0">
                      <input className="form-check-input" type="checkbox" id={`open-${i}`} checked={d.is_open}
                             disabled={!canEdit} onChange={(e) => update(i, { is_open: e.target.checked })} />
                      <label className="form-check-label" htmlFor={`open-${i}`}>{d.is_open ? 'Open' : 'Closed'}</label>
                    </div>
                  </td>
                  <td>
                    {d.is_open && (
                      <div className="d-flex align-items-center gap-2">
                        <input type="time" className="form-control form-control-sm" style={{ width: 120 }} value={d.opening_time}
                               disabled={!canEdit} onChange={(e) => update(i, { opening_time: e.target.value })} />
                        <span>to</span>
                        <input type="time" className="form-control form-control-sm" style={{ width: 120 }} value={d.closing_time}
                               disabled={!canEdit} onChange={(e) => update(i, { closing_time: e.target.value })} />
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {canEdit && <button className="btn btn-primary mt-3" disabled={busy} onClick={save}>Save opening hours</button>}
      </div>
    </div>
  )
}

const EMPTY_SERVICE = { name: '', description: '', price: '', duration_minutes: '', is_active: true }

function ServiceForm({ service, onClose, onSave, busy, error }) {
  const [form, setForm] = useState({ ...EMPTY_SERVICE, ...service, duration_minutes: service.duration_minutes ?? '' })
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })
  return (
    <Modal title={service.id ? 'Edit service' : 'New service'} onClose={onClose}
           footer={<>
             <button className="btn btn-outline-secondary" onClick={onClose}>Cancel</button>
             <button className="btn btn-primary" disabled={busy} onClick={() => onSave(form)}>{busy ? 'Saving...' : 'Save'}</button>
           </>}>
      <ErrorAlert error={error} />
      <div className="mb-3"><label className="form-label">Name</label>
        <input className="form-control" value={form.name} onChange={set('name')} maxLength={150} /></div>
      <div className="mb-3"><label className="form-label">Description</label>
        <textarea className="form-control" rows={3} value={form.description || ''} onChange={set('description')}></textarea></div>
      <div className="row g-3 mb-3">
        <div className="col-sm-7"><label className="form-label">Price (shown to customers as written)</label>
          <input className="form-control" value={form.price || ''} onChange={set('price')} maxLength={100} placeholder="e.g. From INR 15,000" /></div>
        <div className="col-sm-5"><label className="form-label">Duration (min)</label>
          <input type="number" min={5} className="form-control" value={form.duration_minutes} onChange={set('duration_minutes')} /></div>
      </div>
      <div className="form-check">
        <input className="form-check-input" type="checkbox" id="svc-active" checked={form.is_active} onChange={set('is_active')} />
        <label className="form-check-label" htmlFor="svc-active">Active (offered to customers)</label>
      </div>
    </Modal>
  )
}

function ServicesCard({ canEdit }) {
  const { data, loading, error, reload, setError } = useLoader(getServices, [], [])
  const [success, setSuccess] = useFlash()
  const [run, busy] = useMutation(setError, setSuccess)
  const [editing, setEditing] = useState(null)
  const rows = data || []

  async function save(form) {
    const payload = {
      name: form.name.trim(), description: (form.description || '').trim() || null, price: (form.price || '').trim() || null,
      duration_minutes: form.duration_minutes === '' ? null : Number(form.duration_minutes), is_active: form.is_active,
    }
    const ok = await run(() => (form.id ? updateService(form.id, payload) : createService(payload)), 'Service saved.', reload)
    if (ok) setEditing(null)
  }
  const remove = (s) => window.confirm(`Delete the service "${s.name}"?`) && run(() => deleteService(s.id), 'Service deleted.', reload)

  return (
    <div className="card border-0 shadow-sm mb-4">
      <div className="card-body">
        <div className="d-flex justify-content-between align-items-center mb-2">
          <h5 className="mb-0">Services and prices</h5>
          {canEdit && <button className="btn btn-sm btn-primary" onClick={() => setEditing(EMPTY_SERVICE)}><i className="bi bi-plus-lg me-1"></i>Add</button>}
        </div>
        <p className="small text-muted">Leave the price empty if you don't want Ava to quote one.</p>
        <ErrorAlert error={error} onClose={() => setError('')} />
        <SuccessAlert message={success} />
        {loading && !rows.length ? <Loading /> : (
          <div className="table-responsive">
            <table className="table table-hover align-middle small mb-0">
              <thead className="table-light"><tr><th>Name</th><th>Description</th><th>Price</th><th>Duration</th><th>Active</th>{canEdit && <th></th>}</tr></thead>
              <tbody>
                {rows.map((s) => (
                  <tr key={s.id} className={s.is_active ? '' : 'text-muted'}>
                    <td className="fw-semibold">{s.name}</td>
                    <td style={{ maxWidth: 320 }}><div className="text-truncate" title={s.description || ''}>{s.description || '-'}</div></td>
                    <td>{s.price || '-'}</td>
                    <td>{s.duration_minutes ? `${s.duration_minutes} min` : '-'}</td>
                    <td>{s.is_active ? <i className="bi bi-check-circle-fill text-success"></i> : <i className="bi bi-x-circle"></i>}</td>
                    {canEdit && (
                      <td className="text-end text-nowrap">
                        <button className="btn btn-sm btn-outline-secondary me-1" onClick={() => setEditing(s)}><i className="bi bi-pencil"></i></button>
                        <button className="btn btn-sm btn-outline-danger" disabled={busy} onClick={() => remove(s)}><i className="bi bi-trash"></i></button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      {editing && <ServiceForm service={editing} busy={busy} error={error} onClose={() => setEditing(null)} onSave={save} />}
    </div>
  )
}

export default function Business() {
  const canEdit = isAdminRole()
  return (
    <>
      <PageHeader title="Business" icon="bi-shop" />
      {!canEdit && <div className="alert alert-info py-2 small">You can view these settings. Only admins can change them.</div>}
      <SettingsCard canEdit={canEdit} />
      <HoursCard canEdit={canEdit} />
      <ServicesCard canEdit={canEdit} />
    </>
  )
}
