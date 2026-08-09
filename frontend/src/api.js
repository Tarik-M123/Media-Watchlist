const BASE_URL = 'http://127.0.0.1:8000'

const TOKEN_KEY = 'mw_token'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY)
}

// FastAPI reports errors two different ways: HTTPException gives
// {detail: "text"}, validation failures give {detail: [{msg, loc}, ...]}.
function messageFrom(payload, status) {
  const detail = payload?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const parts = detail
      .map((d) => d.msg?.replace(/^Value error, /, ''))
      .filter(Boolean)
    if (parts.length) return parts.join('; ')
  }
  return `Request failed (${status})`
}

async function request(path, { method = 'GET', body, auth = true, signal } = {}) {
  const headers = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (auth) {
    const token = getToken()
    if (token) headers.Authorization = `Bearer ${token}`
  }

  let response
  try {
    response = await fetch(BASE_URL + path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    })
  } catch (e) {
    // An aborted request is a superseded keystroke, not a failure — rethrow it
    // so callers can tell the two apart.
    if (e.name === 'AbortError') throw e
    throw new Error('Cannot reach the API — is the backend running on port 8000?')
  }

  if (response.status === 204) return null

  const payload = await response.json().catch(() => null)
  if (!response.ok) {
    const error = new Error(messageFrom(payload, response.status))
    error.status = response.status
    throw error
  }
  return payload
}

export const api = {
  register: (email) =>
    request('/auth/register', { method: 'POST', body: { email }, auth: false }),
  login: (email) =>
    request('/auth/login', { method: 'POST', body: { email }, auth: false }),
  dashboard: () => request('/dashboard/'),
  createItem: (item) => request('/watchlist/', { method: 'POST', body: item }),
  updateItem: (id, patch) =>
    request(`/watchlist/${id}`, { method: 'PATCH', body: patch }),
  deleteItem: (id) => request(`/watchlist/${id}`, { method: 'DELETE' }),
  searchMedia: (query, signal) =>
    request(`/media/search?q=${encodeURIComponent(query)}`, { signal }),
  watchProviders: (mediaType, tmdbId) =>
    request(`/media/providers/${mediaType}/${tmdbId}`),
}
