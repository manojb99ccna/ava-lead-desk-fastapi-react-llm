import { badgeClass, label } from '../../utils/format.js'

export function PageHeader({ title, icon, children }) {
  return (
    <div className="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-4">
      <h3 className="mb-0">
        {icon && <i className={`bi ${icon} me-2 text-primary`}></i>}
        {title}
      </h3>
      <div className="d-flex flex-wrap gap-2">{children}</div>
    </div>
  )
}

export function StatusBadge({ value }) {
  return <span className={`${badgeClass(value)} text-capitalize`}>{label(value)}</span>
}

export function Loading() {
  return (
    <div className="text-center py-5">
      <div className="spinner-border text-primary"></div>
    </div>
  )
}

export function ErrorAlert({ error, onClose }) {
  if (!error) return null
  return (
    <div className="alert alert-danger d-flex justify-content-between align-items-start">
      <span>
        <i className="bi bi-exclamation-triangle me-2"></i>
        {error}
      </span>
      {onClose && <button type="button" className="btn-close" onClick={onClose}></button>}
    </div>
  )
}

export function Empty({ text = 'Nothing here yet.' }) {
  return <div className="text-center text-muted py-5">{text}</div>
}

export function RefreshButton({ onClick, loading }) {
  return (
    <button className="btn btn-outline-secondary btn-sm" onClick={onClick} disabled={loading}>
      <i className={`bi bi-arrow-clockwise ${loading ? 'spin' : ''}`}></i> Refresh
    </button>
  )
}

// Simple controlled modal (no Bootstrap JS needed).
export function Modal({ title, onClose, children, footer, size = '' }) {
  return (
    <>
      <div className="modal d-block" tabIndex="-1" role="dialog" onClick={onClose}>
        <div className={`modal-dialog modal-dialog-scrollable ${size}`} onClick={(e) => e.stopPropagation()}>
          <div className="modal-content">
            <div className="modal-header">
              <h5 className="modal-title">{title}</h5>
              <button type="button" className="btn-close" onClick={onClose}></button>
            </div>
            <div className="modal-body">{children}</div>
            {footer && <div className="modal-footer">{footer}</div>}
          </div>
        </div>
      </div>
      <div className="modal-backdrop show"></div>
    </>
  )
}
