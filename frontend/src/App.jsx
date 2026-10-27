import { useState, useEffect } from 'react'
import './styles/App.css'
import StatusCard from './components/StatusCard'
import TradesTable from './components/TradesTable'
import SignalsList from './components/SignalsList'
import ConfigPanel from './components/ConfigPanel'

const API_BASE = ''

function App() {
  const [status, setStatus] = useState(null)
  const [trades, setTrades] = useState([])
  const [signals, setSignals] = useState([])
  const [loading, setLoading] = useState(true)
  const [botApiKey, setBotApiKey] = useState('')
  const [showApiInfo, setShowApiInfo] = useState(false)

  useEffect(() => {
    fetchStatus()
    const interval = setInterval(fetchStatus, 10000)
    return () => clearInterval(interval)
  }, [])

  const fetchStatus = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/status`)
      const data = await res.json()
      setStatus(data)
      setLoading(false)
    } catch (err) {
      console.error('Failed to fetch status:', err)
    }
  }

  const fetchTrades = async () => {
    if (!botApiKey) return
    try {
      const res = await fetch(`${API_BASE}/api/trades`, {
        headers: { 'X-API-Key': botApiKey }
      })
      const data = await res.json()
      setTrades(data.slice(0, 10))
    } catch (err) {
      console.error('Failed to fetch trades:', err)
    }
  }

  const fetchSignals = async () => {
    if (!botApiKey) return
    try {
      const res = await fetch(`${API_BASE}/api/signals`, {
        headers: { 'X-API-Key': botApiKey }
      })
      const data = await res.json()
      setSignals(data.slice(0, 5))
    } catch (err) {
      console.error('Failed to fetch signals:', err)
    }
  }

  const handleAuth = (e) => {
    e.preventDefault()
    fetchTrades()
    fetchSignals()
  }

  if (loading) {
    return (
      <div className="app">
        <div className="loading">Loading...</div>
      </div>
    )
  }

  return (
    <div className="app">
      <header className="header">
        <h1>🚀 Binance Trading Bot</h1>
        <div className={`status-badge ${status?.dry_run ? 'dry-run' : 'live'}`}>
          {status?.dry_run ? '🧪 DRY RUN' : '✅ LIVE'}
        </div>
      </header>

      <div className="info-banner">
        <p>
          🔑 <strong>Bot API Key</strong> eingeben für Zugriff auf Trades & Signale. 
          Nicht mit Binance API Keys verwechseln!
          <button onClick={() => setShowApiInfo(!showApiInfo)} className="info-button">
            {showApiInfo ? '▼' : '▶'} Mehr Info
          </button>
        </p>
        {showApiInfo && (
          <div className="info-details">
            <p><strong>So erstellst du einen Bot API Key:</strong></p>
            <ol>
              <li>Server/.env-Datei öffnen</li>
              <li><code>API_KEYS=admin:dein-geheimer-key</code> hinzufügen</li>
              <li>Bot neu starten</li>
              <li>Diesen Key hier eingeben (z.B. <code>dein-geheimer-key</code>)</li>
            </ol>
            <p style={{ marginTop: '10px', fontSize: '0.85rem', color: '#a0a0b0' }}>
              ⚠️ Binance API Key/Secret werden nur serverseitig in der .env-Datei gespeichert!
            </p>
          </div>
        )}
      </div>

      <form className="auth-form" onSubmit={handleAuth}>
        <input
          type="password"
          placeholder="Bot API Key (z.B. admin-secret-123)"
          value={botApiKey}
          onChange={(e) => setBotApiKey(e.target.value)}
          className="auth-input"
        />
        <button type="submit" className="auth-button">Connect</button>
      </form>

      <div className="dashboard">
        <StatusCard status={status} />
        <SignalsList signals={signals} />
        <TradesTable trades={trades} />
        <ConfigPanel apiKey={botApiKey} />
      </div>
    </div>
  )
}

export default App
