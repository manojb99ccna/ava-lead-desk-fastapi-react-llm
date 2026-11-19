import { useState } from 'react'
import { createUser, getUsers, updateUser } from '../../services/api.js'
import { getAdmin } from '../../services/auth.js'
import { formatDateTime } from '../../utils/format.js'
import { Empty, ErrorAlert, Loading, Modal, PageHeader, RefreshButton, StatusBadge } from '../../components/admin/ui.jsx'
import { SuccessAlert, useFlash, useLoader, useMutation } from '../../components/admin/shared.jsx'

function UserForm({ user, onClose, onSave, busy, error }) {
  const isNew = !user.id
  const [form, setForm] = useState({ username: user.username || '', name: user.name || '', role: user.role || 'staff',
                                     is_active: user.is_active ?? true, password: '' })
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })
  const self = user.id === getAdmin()?.id

  return (
    <Modal title={isNew ? 'New user' : `Edit ${user.username}`} onClose={onClose}
           footer={<>
             <button className="btn btn-outline-secondary" onClick={onClose}>Cancel</button>
             <button className="btn btn-primary" disabled={busy} onClick={() => onSave(form)}>{busy ? 'Saving...' : 'Save'}</button>
           </>}>
      <ErrorAlert error={error} />
      {isNew && (
        <div className="mb-3">
          <label className="form-label">Username</label>
          <input className="form-control" value={form.username} onChange={set('username')} maxLength={50} autoComplete="off" />
          <div className="form-text">Letters, numbers, dot, dash, underscore.</div>
        </div>
      )}
      <div className="mb-3">
        <label className="form-label">Name</label>
        <input className="form-control" value={form.name} onChange={set('name')} maxLength={100} />
      </div>
      <div className="mb-3">
        <label className="form-label">Role</label>
        <select className="form-select" value={form.role} onChange={set('role')} disabled={self}>
          <option value="staff">Staff: appointments, leads, handoffs</option>
          <option value="admin">Admin: everything, including settings and users</option>
        </select>
      </div>
      <div className="mb-3">
        <label className="form-label">{isNew ? 'Password' : 'New password (leave empty to keep)'}</label>
        <input type="password" className="form-control" value={form.password} onChange={set('password')} minLength={8} autoComplete="new-password" />
        <div className="form-text">At least 8 characters.</div>
      </div>
      {!isNew && (
        <div className="form-check">
          <input className="form-check-input" type="checkbox" id="user-active" checked={form.is_active} onChange={set('is_active')} disabled={self} />
          <label className="form-check-label" htmlFor="user-active">Active (can log in)</label>
        </div>
      )}
    </Modal>
  )
}

export default function Users() {
  const { data, loading, error, reload, setError } = useLoader(getUsers, [], [])
  const [success, setSuccess] = useFlash()
  const [run, busy] = useMutation(setError, setSuccess)
  const [editing, setEditing] = useState(null)
  const rows = data || []

  async function save(form) {
    let fn
    if (!editing.id) {
      fn = () => createUser({ username: form.username.trim(), password: form.password, name: form.name.trim() || null, role: form.role })
    } else {
      const payload = { name: form.name.trim() || null, role: form.role, is_active: form.is_active }
      if (form.password) payload.password = form.password
      fn = () => updateUser(editing.id, payload)
    }
    const ok = await run(fn, 'User saved.', reload)
    if (ok) setEditing(null)
  }

  return (
    <>
      <PageHeader title="Users" icon="bi-person-gear">
        <RefreshButton onClick={reload} loading={loading} />
        <button className="btn btn-primary btn-sm" onClick={() => setEditing({})}><i className="bi bi-plus-lg me-1"></i>New user</button>
      </PageHeader>
      <ErrorAlert error={error} onClose={() => setError('')} />
      <SuccessAlert message={success} onClose={() => setSuccess('')} />

      <div className="card border-0 shadow-sm">
        {loading && !rows.length ? <Loading /> : !rows.length ? <Empty /> : (
          <div className="table-responsive">
            <table className="table table-hover align-middle mb-0 small">
              <thead className="table-light">
                <tr><th>Username</th><th>Name</th><th>Role</th><th>Status</th><th>Last login</th><th className="text-end">Actions</th></tr>
              </thead>
              <tbody>
                {rows.map((u) => (
                  <tr key={u.id}>
                    <td className="fw-semibold">{u.username}</td>
                    <td>{u.name || '-'}</td>
                    <td><StatusBadge value={u.role} /></td>
                    <td>{u.is_active ? <span className="badge text-bg-success">active</span> : <span className="badge text-bg-secondary">disabled</span>}</td>
                    <td className="text-nowrap">{formatDateTime(u.last_login_at)}</td>
                    <td className="text-end">
                      <button className="btn btn-sm btn-outline-secondary" onClick={() => setEditing(u)}><i className="bi bi-pencil"></i></button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      {editing && <UserForm user={editing} busy={busy} error={error} onClose={() => setEditing(null)} onSave={save} />}
    </>
  )
}
