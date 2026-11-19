import { clearSession, getToken } from './auth.js'
import { API_URL } from '../config.js'

// Admin pages go through the Vite proxy (/api -> backend). The chat widget calls the backend URL directly.
const ADMIN_BASE = '/api'

export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.status = status
  }
}

async function request(base, path, options = {}) {
  const token = getToken()
  const headers = { 'Content-Type': 'application/json' }
  if (token && base === ADMIN_BASE) headers.Authorization = `Bearer ${token}`

  let res
  try {
    res = await fetch(`${base}${path}`, { ...options, headers })
  } catch {
    throw new ApiError('Could not reach the server. Please check your connection.', 0)
  }
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    if (res.status === 401 && token && base === ADMIN_BASE) {
      clearSession()
      if (!location.pathname.startsWith('/admin/login')) location.assign('/admin/login')
    }
    const detail = Array.isArray(data.detail)
      ? data.detail
          .map((d) => {
            const field = Array.isArray(d.loc) ? d.loc.filter((p) => p !== 'body').join('.') : ''
            const msg = String(d.msg || '').replace(/^Value error, /, '')
            return field ? `${field}: ${msg}` : msg
          })
          .join('; ')
      : data.detail
    const message =
      res.status === 429
        ? 'Too many requests. Please wait a moment and try again.'
        : detail || `Request failed (${res.status})`
    throw new ApiError(typeof message === 'string' ? message : 'Request failed', res.status)
  }
  return data
}

const admin = (path, options) => request(ADMIN_BASE, path, options)
const json = (method, body) => ({ method, body: JSON.stringify(body ?? {}) })
const qs = (params = {}) => {
  const entries = Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')
  return entries.length ? `?${new URLSearchParams(entries)}` : ''
}

// --- Public chat (widget) ---
const publicApi = (path, options) => request(`${API_URL}/api`, path, options)
export const sendChat = (payload) => publicApi('/chat', json('POST', payload))
export const getChatHistory = (sessionId) => publicApi(`/chat/history${qs({ session_id: sessionId })}`)
export const endChat = (sessionId) => publicApi('/chat/end', json('POST', { session_id: sessionId }))
export const getPublicInfo = () => publicApi('/chat/info')

// --- Auth / users ---
export const getHealth = () => admin('/health')
export const adminLogin = (username, password) => admin('/admin/login', json('POST', { username, password }))
export const getAdminMe = () => admin('/admin/me')
export const changePassword = (current_password, new_password) =>
  admin('/admin/me/password', json('POST', { current_password, new_password }))
export const getUsers = () => admin('/admin/users')
export const createUser = (data) => admin('/admin/users', json('POST', data))
export const updateUser = (id, data) => admin(`/admin/users/${id}`, json('PATCH', data))

// --- Dashboard ---
export const getDashboard = () => admin('/admin/dashboard')

// --- Appointments ---
export const getAppointments = (params) => admin(`/admin/appointments${qs(params)}`)
export const getAppointment = (id) => admin(`/admin/appointments/${id}`)
export const createAppointment = (data) => admin('/admin/appointments', json('POST', data))
export const updateAppointment = (id, data) => admin(`/admin/appointments/${id}`, json('PATCH', data))
export const rescheduleAppointment = (id, new_date, new_time) =>
  admin(`/admin/appointments/${id}/reschedule`, json('POST', { new_date, new_time }))
export const cancelAppointment = (id, reason) => admin(`/admin/appointments/${id}/cancel`, json('POST', { reason }))
export const getAvailability = (selected_date) => admin(`/admin/appointments/availability${qs({ selected_date })}`)

// --- Customers ---
export const getCustomers = (q) => admin(`/admin/customers${qs({ q })}`)
export const getCustomer = (id) => admin(`/admin/customers/${id}`)

// --- Leads ---
export const getLeads = (params) => admin(`/admin/leads${qs(params)}`)
export const updateLead = (id, data) => admin(`/admin/leads/${id}`, json('PATCH', data))
export const deleteLead = (id) => admin(`/admin/leads/${id}`, { method: 'DELETE' })

// --- FAQs ---
export const getFaqs = () => admin('/admin/faqs')
export const searchFaqs = (q) => admin(`/admin/faqs/search${qs({ q })}`)
export const createFaq = (faqData) => admin('/admin/faqs', json('POST', faqData))
export const updateFaq = (id, faqData) => admin(`/admin/faqs/${id}`, json('PUT', faqData))
export const deleteFaq = (id) => admin(`/admin/faqs/${id}`, { method: 'DELETE' })

// --- Conversations ---
export const getConversations = (params) => admin(`/admin/conversations${qs(params)}`)
export const getConversationMessages = (id) => admin(`/admin/conversations/${id}/messages`)

// --- Handoffs ---
export const getHandoffs = (status) => admin(`/admin/handoffs${qs({ status })}`)
export const updateHandoff = (id, data) => admin(`/admin/handoffs/${id}`, json('PATCH', data))

// --- Business ---
export const getBusinessSettings = () => admin('/admin/business/settings')
export const updateBusinessSettings = (data) => admin('/admin/business/settings', json('PUT', data))
export const getBusinessHours = () => admin('/admin/business/hours')
export const updateBusinessHours = (days) => admin('/admin/business/hours', json('PUT', days))
export const getServices = () => admin('/admin/business/services')
export const createService = (data) => admin('/admin/business/services', json('POST', data))
export const updateService = (id, data) => admin(`/admin/business/services/${id}`, json('PUT', data))
export const deleteService = (id) => admin(`/admin/business/services/${id}`, { method: 'DELETE' })
