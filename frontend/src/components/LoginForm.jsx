import { useState } from 'react'
import { login } from '../api'

export default function LoginForm({ onLogin }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setSubmitting(true)
    setError('')
    try {
      onLogin(await login(username, password))
    } catch (err) {
      setError(err.message)
      setPassword('')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form className="auth-form login-form" onSubmit={handleSubmit}>
      <h2>🔐 Anmelden</h2>
      <input
        type="text"
        aria-label="Benutzername"
        placeholder="Benutzername"
        autoComplete="username"
        value={username}
        onChange={(e) => setUsername(e.target.value)}
        className="auth-input"
        required
      />
      <input
        type="password"
        aria-label="Passwort"
        placeholder="Passwort"
        autoComplete="current-password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        className="auth-input"
        required
      />
      {error && <p className="login-error" role="alert">{error}</p>}
      <button type="submit" className="auth-button" disabled={submitting}>
        {submitting ? 'Anmelden…' : 'Anmelden'}
      </button>
    </form>
  )
}
