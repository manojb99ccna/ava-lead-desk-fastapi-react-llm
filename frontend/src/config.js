// App-wide settings. Values come from frontend/.env
// VITE_API_URL empty or unset = same origin (production behind nginx, which proxies /api).
export const API_URL = (import.meta.env.VITE_API_URL ?? '').replace(/\/$/, '')

export const CHAT_API_URL = `${API_URL}/api/chat`
