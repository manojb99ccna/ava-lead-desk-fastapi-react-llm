import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { clearSession, getAdmin } from '../services/auth.js'
import { changePassword } from '../services/api.js'
import { ErrorAlert, Modal, StatusBadge } from '../components/admin/ui.jsx'
import { SuccessAlert } from '../components/admin/shared.jsx'

const NAV = [
  { to: '/admin', label: 'Dashboard', icon: 'bi-speedometer2', end: true },
  { to: '/admin/appointments', label: 'Appointments', icon: 'bi-calendar-check' },
  { to: '/admin/handoffs', label: 'Handoffs', icon: 'bi-person-raised-hand' },
  { to: '/admin/leads', label: 'Leads', icon: 'bi-funnel' },
  { to: '/admin/customers', label: 'Customers', icon: 'bi-people' },
  { to: '/admin/conversations', label: 'Conversations', icon: 'bi-chat-dots' },
  { to: '/admin/faqs', label: 'FAQs', icon: 'bi-question-circle' },
  { to: '/admin/business', label: 'Business', icon: 'bi-shop' },
  { to: '/admin/users', label: 'Users', icon: 'bi-person-gear', adminOnly: true },
]

function PasswordModal({ onClose }) {
  const [form, setForm] = useState({ current: '', next: '', confirm: '' })
  const [error, setError] = useState('')
  const [done, setDone] = useState('')
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })

  async function submit(e) {
    e.preventDefault()
    setError('')
    if (form.next.length < 8) return setError('New password must be at least 8 characters.')
    if (form.next !== form.confirm) return setError('The new passwords do not match.')
    setBusy(true)
    try {
      await changePassword(form.current, form.next)
      setDone('Your password has been changed.')
      setForm({ current: '', next: '', confirm: '' })
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal title="Change my password" onClose={onClose}>
      <ErrorAlert error={error} />
      <SuccessAlert message={done} />
      <form onSubmit={submit}>
        <div className="mb-3">
          <label className="form-label">Current password</label>
          <input type="password" className="form-control" value={form.current} onChange={set('current')} required autoComplete="current-password" />
        </div>
        <div className="mb-3">
          <label className="form-label">New password (min 8)</label>
          <input type="password" className="form-control" value={form.next} onChange={set('next')} required minLength={8} autoComplete="new-password" />
        </div>
        <div className="mb-3">
          <label className="form-label">Repeat new password</label>
          <input type="password" className="form-control" value={form.confirm} onChange={set('confirm')} required autoComplete="new-password" />
        </div>
        <div className="d-flex justify-content-end gap-2">
          <button type="button" className="btn btn-outline-secondary" onClick={onClose}>Close</button>
          <button className="btn btn-primary" disabled={busy}>{busy ? 'Saving...' : 'Change password'}</button>
        </div>
      </form>
    </Modal>
  )
}

export default function AdminLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const admin = getAdmin()
  const [menuOpen, setMenuOpen] = useState(false)
  const [showPassword, setShowPassword] = useState(false)

  useEffect(() => setMenuOpen(false), [location.pathname])

  function logout() {
    clearSession()
    navigate('/admin/login')
  }

  const items = NAV.filter((n) => !n.adminOnly || admin?.role === 'admin')

  return (
    <div className="d-flex flex-column min-vh-100 bg-light">
      <nav className="navbar navbar-dark bg-dark px-3 sticky-top">
        <div className="d-flex align-items-center">
          <button className="btn btn-outline-light btn-sm d-lg-none me-2" onClick={() => setMenuOpen((v) => !v)} aria-label="Toggle menu">
            <i className={`bi ${menuOpen ? 'bi-x-lg' : 'bi-list'}`}></i>
          </button>
          <span className="navbar-brand fw-bold mb-0">
            <i className="bi bi-headset me-2"></i>Ava AI Admin
          </span>
        </div>
        <div className="d-flex align-items-center gap-2">
          <span className="text-white-50 small d-none d-sm-inline">
            <i className="bi bi-person-circle me-1"></i>
            {admin?.name || admin?.username}
          </span>
          {admin?.role && <StatusBadge value={admin.role} />}
          <button className="btn btn-outline-light btn-sm" onClick={() => setShowPassword(true)} title="Change my password">
            <i className="bi bi-key"></i>
          </button>
          <button className="btn btn-outline-light btn-sm" onClick={logout}>
            <i className="bi bi-box-arrow-right"></i>
            <span className="d-none d-sm-inline ms-1">Logout</span>
          </button>
        </div>
      </nav>

      <div className="d-flex flex-grow-1 position-relative">
        {menuOpen && (
          <div className="d-lg-none position-fixed top-0 start-0 w-100 h-100 bg-dark bg-opacity-50" style={{ zIndex: 1029 }} onClick={() => setMenuOpen(false)}></div>
        )}
        <aside
          className={`bg-white border-end p-3 shadow-sm flex-shrink-0 ${menuOpen ? 'd-block position-fixed h-100 overflow-auto' : 'd-none'} d-lg-block`}
          style={{ width: 240, zIndex: 1030, top: menuOpen ? 56 : undefined, left: 0 }}
        >
          <ul className="nav nav-pills flex-column gap-1">
            {items.map((n) => (
              <li className="nav-item" key={n.to}>
                <NavLink to={n.to} end={n.end} className={({ isActive }) => `nav-link ${isActive ? 'active' : 'text-dark'}`}>
                  <i className={`bi ${n.icon} me-2`}></i>
                  {n.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </aside>

        <main className="flex-grow-1 p-3 p-md-4" style={{ minWidth: 0 }}>
          <Outlet />
        </main>
      </div>

      {showPassword && <PasswordModal onClose={() => setShowPassword(false)} />}
    </div>
  )
}
