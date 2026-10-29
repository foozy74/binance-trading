// Token nur pro Tab speichern: nach Schließen des Tabs ist eine neue Anmeldung nötig
const TOKEN_KEY = 'auth_token'
export const LOGOUT_EVENT = 'auth:logout'

export const getToken = () => sessionStorage.getItem(TOKEN_KEY)

export function logout() {
  sessionStorage.removeItem(TOKEN_KEY)
  window.dispatchEvent(new Event(LOGOUT_EVENT))
}

export async function login(username, password) {
  const res = await fetch('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password })
  })
  if (res.status === 401) throw new Error('Benutzername oder Passwort falsch')
  if (res.status === 429) throw new Error('Zu viele Fehlversuche, bitte später erneut versuchen')
  if (!res.ok) throw new Error(`Login fehlgeschlagen (HTTP ${res.status})`)
  const { access_token } = await res.json()
  sessionStorage.setItem(TOKEN_KEY, access_token)
  return access_token
}

export async function apiFetch(path, options = {}) {
  const res = await fetch(path, {
    ...options,
    headers: { ...options.headers, Authorization: `Bearer ${getToken()}` }
  })
  // Abgelaufener oder ungültiger Token: zurück zum Login
  if (res.status === 401) {
    logout()
    throw new Error('Sitzung abgelaufen')
  }
  if (!res.ok) {
    // FastAPI liefert lesbare Fehler als {"detail": "..."}; Validierungsfehler sind Listen
    const body = await res.json().catch(() => ({}))
    throw new Error(typeof body.detail === 'string' ? body.detail : `HTTP ${res.status}`)
  }
  return res.json()
}
