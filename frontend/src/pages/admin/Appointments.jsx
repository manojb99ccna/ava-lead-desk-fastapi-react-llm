import { useState } from 'react'
import {
  cancelAppointment, createAppointment, getAppointment, getAppointments, getServices, rescheduleAppointment, updateAppointment,
} from '../../services/api.js'
import { formatDateTime, label } from '../../utils/format.js'
import { Empty, ErrorAlert, Loading, Modal, PageHeader, RefreshButton, StatusBadge } from '../../components/admin/ui.jsx'
import { SlotPicker, SuccessAlert, todayISO, useDebounced, useFlash, useLoader, useMutation } from '../../components/admin/shared.jsx'

const STATUSES = ['pending', 'confirmed', 'completed', 'cancelled', 'no_show']
const EMPTY_FILTERS = { status: '', date_from: '', date_to: '', q: '' }

function Filters({ value, onChange }) {
  const set = (k) => (e) => onChange({ ...value, [k]: e.target.value })
  return (
    <div className="card border-0 shadow-sm mb-3">
      <div className="card-body row g-2 align-items-end">
        <div className="col-6 col-md-2">
          <label className="form-label small mb-1">Status</label>
          <select className="form-select form-select-sm" value={value.status} onChange={set('status')}>
            <option value="">All</option>
            {STATUSES.map((s) => <option key={s} value={s}>{label(s)}</option>)}
          </select>
        </div>
        <div className="col-6 col-md-2">
          <label className="form-label small mb-1">From</label>
          <input type="date" className="form-control form-control-sm" value={value.date_from} onChange={set('date_from')} />
        </div>
        <div className="col-6 col-md-2">
          <label className="form-label small mb-1">To</label>
          <input type="date" className="form-control form-control-sm" value={value.date_to} onChange={set('date_to')} />
        </div>
        <div className="col-6 col-md-4">
          <label className="form-label small mb-1">Search</label>
          <input className="form-control form-control-sm" placeholder="Name, phone, code, service" value={value.q} onChange={set('q')} />
        </div>
        <div className="col-12 col-md-2">
          <button className="btn btn-sm btn-outline-secondary w-100" onClick={() => onChange(EMPTY_FILTERS)}>Clear</button>
        </div>
      </div>
    </div>
  )
}

function NewAppointmentModal({ onClose, onSaved }) {
  const [form, setForm] = useState({ name: '', phone: '', email: '', service: '', appointment_date: '', start_time: '', notes: '' })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const services = useLoader(getServices, [], [])
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })
  const activeServices = (services.data || []).filter((s) => s.is_active)

  async function submit(e) {
    e.preventDefault()
    if (!form.start_time) return setError('Please pick a time slot.')
    setBusy(true)
    setError('')
    try {
      const created = await createAppointment({ ...form, email: form.email || null, notes: form.notes || null })
      onSaved(`Appointment ${created.booking_code} created.`)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal title="New appointment" onClose={onClose} size="modal-lg">
      <ErrorAlert error={error} />
      <form onSubmit={submit} className="row g-3">
        <div className="col-md-6">
          <label className="form-label">Name *</label>
          <input className="form-control" value={form.name} onChange={set('name')} required minLength={2} maxLength={100} />
        </div>
        <div className="col-md-6">
          <label className="form-label">Phone *</label>
          <input className="form-control" value={form.phone} onChange={set('phone')} required minLength={7} maxLength={30} />
        </div>
        <div className="col-md-6">
          <label className="form-label">E-mail</label>
          <input type="email" className="form-control" value={form.email} onChange={set('email')} />
        </div>
        <div className="col-md-6">
          <label className="form-label">Service *</label>
          <input className="form-control" list="service-options" value={form.service} onChange={set('service')} required minLength={2} />
          <datalist id="service-options">
            {activeServices.map((s) => <option key={s.id} value={s.name} />)}
          </datalist>
        </div>
        <div className="col-md-6">
          <label className="form-label">Date *</label>
          <input type="date" className="form-control" min={todayISO()} value={form.appointment_date} onChange={set('appointment_date')} required />
        </div>
        <div className="col-12">
          <label className="form-label">Time *</label>
          <SlotPicker date={form.appointment_date} value={form.start_time} onChange={(t) => setForm((f) => ({ ...f, start_time: t }))} />
        </div>
        <div className="col-12">
          <label className="form-label">Notes</label>
          <textarea className="form-control" rows={2} value={form.notes} onChange={set('notes')} maxLength={2000}></textarea>
        </div>
        <div className="col-12 d-flex justify-content-end gap-2">
          <button type="button" className="btn btn-outline-secondary" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" disabled={busy}>{busy ? 'Saving...' : 'Create appointment'}</button>
        </div>
      </form>
    </Modal>
  )
}

function RescheduleModal({ appointment, onClose, onSaved }) {
  const [date, setDate] = useState('')
  const [time, setTime] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit() {
    setBusy(true)
    setError('')
    try {
      await rescheduleAppointment(appointment.id, date, time)
      onSaved(`Appointment ${appointment.booking_code} rescheduled.`)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      title={`Reschedule ${appointment.booking_code}`}
      onClose={onClose}
      footer={
        <>
          <button className="btn btn-outline-secondary" onClick={onClose}>Close</button>
          <button className="btn btn-primary" disabled={!date || !time || busy} onClick={submit}>{busy ? 'Saving...' : 'Reschedule'}</button>
        </>
      }
    >
      <ErrorAlert error={error} />
      <p className="small text-muted">Currently: {formatDateTime(appointment.appointment_date)} ({appointment.name})</p>
      <label className="form-label">New date</label>
      <input type="date" className="form-control mb-3" min={todayISO()} value={date} onChange={(e) => setDate(e.target.value)} />
      <SlotPicker date={date} value={time} onChange={setTime} />
    </Modal>
  )
}

function CancelModal({ appointment, onClose, onSaved }) {
  const [reason, setReason] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit() {
    setBusy(true)
    setError('')
    try {
      await cancelAppointment(appointment.id, reason.trim() || null)
      onSaved(`Appointment ${appointment.booking_code} cancelled.`)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      title={`Cancel ${appointment.booking_code}?`}
      onClose={onClose}
      footer={
        <>
          <button className="btn btn-outline-secondary" onClick={onClose}>Keep it</button>
          <button className="btn btn-danger" disabled={busy} onClick={submit}>{busy ? 'Cancelling...' : 'Cancel appointment'}</button>
        </>
      }
    >
      <ErrorAlert error={error} />
      <p>Cancel the appointment of <strong>{appointment.name}</strong> on {formatDateTime(appointment.appointment_date)}?</p>
      <label className="form-label">Reason (optional)</label>
      <textarea className="form-control" rows={2} maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)}></textarea>
    </Modal>
  )
}

function DetailsModal({ id, onClose }) {
  const { data, loading, error } = useLoader(() => getAppointment(id), [id])
  const a = data?.appointment
  return (
    <Modal title="Appointment details" onClose={onClose} size="modal-lg">
      <ErrorAlert error={error} />
      {loading ? <Loading /> : a && (
        <>
          <dl className="row small">
            <dt className="col-4 col-md-3">Booking code</dt><dd className="col-8 col-md-9"><code>{a.booking_code}</code></dd>
            <dt className="col-4 col-md-3">Customer</dt><dd className="col-8 col-md-9">{a.name} · {a.phone}{a.email ? ` · ${a.email}` : ''}</dd>
            <dt className="col-4 col-md-3">Service</dt><dd className="col-8 col-md-9">{a.service}</dd>
            <dt className="col-4 col-md-3">When</dt><dd className="col-8 col-md-9">{formatDateTime(a.appointment_date)} ({a.duration_minutes} min)</dd>
            <dt className="col-4 col-md-3">Status</dt><dd className="col-8 col-md-9"><StatusBadge value={a.status} /></dd>
            <dt className="col-4 col-md-3">Source</dt><dd className="col-8 col-md-9">{label(a.source)}</dd>
            <dt className="col-4 col-md-3">Notes</dt><dd className="col-8 col-md-9" style={{ whiteSpace: 'pre-wrap' }}>{a.notes || '-'}</dd>
            <dt className="col-4 col-md-3">Created</dt><dd className="col-8 col-md-9">{formatDateTime(a.created_at)}</dd>
          </dl>
          <h6>History</h6>
          {!data.history.length ? <Empty text="No history recorded." /> : (
            <ul className="list-group small">
              {data.history.map((h) => (
                <li key={h.id} className="list-group-item">
                  <div className="d-flex flex-wrap justify-content-between gap-2">
                    <span className="fw-semibold text-capitalize">{label(h.action)}</span>
                    <span className="text-muted">{formatDateTime(h.created_at)} · {h.actor || '-'}</span>
                  </div>
                  {(h.old_status || h.new_status) && h.old_status !== h.new_status && (
                    <div>Status: {label(h.old_status)} → {label(h.new_status)}</div>
                  )}
                  {h.new_appointment_date && h.old_appointment_date !== h.new_appointment_date && (
                    <div>Time: {formatDateTime(h.old_appointment_date)} → {formatDateTime(h.new_appointment_date)}</div>
                  )}
                  {h.note && <div className="text-muted">{h.note}</div>}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </Modal>
  )
}

export default function Appointments() {
  const [filters, setFilters] = useState(EMPTY_FILTERS)
  const query = useDebounced(filters)
  const { data, loading, error, reload, setError } = useLoader(() => getAppointments(query), [JSON.stringify(query)], [])
  const [success, setSuccess] = useFlash()
  const [run, busy] = useMutation(setError, setSuccess)
  const [modal, setModal] = useState(null) // {type, appointment}
  const rows = data || []

  const closeModal = () => setModal(null)
  const saved = (msg) => {
    setModal(null)
    setSuccess(msg)
    reload()
  }
  const changeStatus = (a, status) =>
    run(() => updateAppointment(a.id, { status }), `Status of ${a.booking_code} changed to ${label(status)}.`, reload)
  const editable = (a) => a.status === 'pending' || a.status === 'confirmed'

  return (
    <>
      <PageHeader title="Appointments" icon="bi-calendar-check">
        <RefreshButton onClick={reload} loading={loading} />
        <button className="btn btn-primary btn-sm" onClick={() => setModal({ type: 'new' })}>
          <i className="bi bi-plus-lg me-1"></i>New appointment
        </button>
      </PageHeader>
      <ErrorAlert error={error} onClose={() => setError('')} />
      <SuccessAlert message={success} onClose={() => setSuccess('')} />
      <Filters value={filters} onChange={setFilters} />

      <div className="card border-0 shadow-sm">
        {loading && !rows.length ? <Loading /> : !rows.length ? <Empty text="No appointments match these filters." /> : (
          <div className="table-responsive">
            <table className="table table-hover align-middle mb-0 small">
              <thead className="table-light">
                <tr>
                  <th>Code</th><th>Name</th><th>Phone</th><th>Service</th><th>Date / time</th><th>Status</th><th>Source</th><th className="text-end">Actions</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((a) => (
                  <tr key={a.id}>
                    <td><code>{a.booking_code}</code></td>
                    <td className="fw-semibold">{a.name}</td>
                    <td className="text-nowrap">{a.phone}</td>
                    <td>{a.service}</td>
                    <td className="text-nowrap">{formatDateTime(a.appointment_date)}</td>
                    <td><StatusBadge value={a.status} /></td>
                    <td className="text-capitalize">{label(a.source)}</td>
                    <td className="text-end">
                      <div className="d-flex justify-content-end gap-1">
                        <select className="form-select form-select-sm" style={{ width: 130 }} value={a.status} disabled={busy}
                          onChange={(e) => changeStatus(a, e.target.value)} aria-label="Change status">
                          {STATUSES.map((s) => <option key={s} value={s}>{label(s)}</option>)}
                        </select>
                        <button className="btn btn-sm btn-outline-secondary" title="Details" onClick={() => setModal({ type: 'details', appointment: a })}>
                          <i className="bi bi-eye"></i>
                        </button>
                        <button className="btn btn-sm btn-outline-primary" title="Reschedule" disabled={!editable(a)} onClick={() => setModal({ type: 'reschedule', appointment: a })}>
                          <i className="bi bi-calendar2-week"></i>
                        </button>
                        <button className="btn btn-sm btn-outline-danger" title="Cancel" disabled={!editable(a)} onClick={() => setModal({ type: 'cancel', appointment: a })}>
                          <i className="bi bi-x-circle"></i>
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {modal?.type === 'new' && <NewAppointmentModal onClose={closeModal} onSaved={saved} />}
      {modal?.type === 'reschedule' && <RescheduleModal appointment={modal.appointment} onClose={closeModal} onSaved={saved} />}
      {modal?.type === 'cancel' && <CancelModal appointment={modal.appointment} onClose={closeModal} onSaved={saved} />}
      {modal?.type === 'details' && <DetailsModal id={modal.appointment.id} onClose={closeModal} />}
    </>
  )
}
