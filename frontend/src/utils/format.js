export function formatDateTime(value) {
  if (!value) return '-'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return String(value)
  return d.toLocaleString('en-IN', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export function formatDate(value) {
  if (!value) return '-'
  const d = new Date(value.length === 10 ? `${value}T00:00:00` : value)
  return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
}

export function formatTime(value) {
  if (!value) return ''
  return new Date(value).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })
}

const BADGES = {
  pending: 'warning', confirmed: 'primary', completed: 'success', cancelled: 'secondary', no_show: 'dark',
  new: 'info', contacted: 'primary', qualified: 'warning', converted: 'success', lost: 'secondary',
  open: 'danger', in_progress: 'warning', resolved: 'success',
  active: 'success', handoff: 'danger', closed: 'secondary',
  llm: 'primary', rules: 'secondary', admin: 'dark', staff: 'info',
}

export function badgeClass(status) {
  return `badge text-bg-${BADGES[status] || 'light'}`
}

export const label = (value) => (value ? String(value).replace(/_/g, ' ') : '-')
