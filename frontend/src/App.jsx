import { useState, useEffect } from 'react'
import './styles/App.css'
import StatusCard from './components/StatusCard'
import TradesTable from './components/TradesTable'
import SignalsList from './components/SignalsList'
import ConfigPanel from './components/ConfigPanel'
import LoginForm from './components/LoginForm'
import { apiFetch, getToken, logout, LOGOUT_EVENT } from './api'

function App() {
  const [token, setToken] = useState(getToken())
  const [status, setStatus] = useState(null)
  const [trades, setTrades] = useState([])
  const [signals, setSignals] = useState([])

  useEffect(() => {
    const handleLogout = () => setToken(null)
    window.addEventListener(LOGOUT_EVENT, handleLogout)
    return () => window.removeEventListener(LOGOUT_EVENT, handleLogout)
  }, [])

  useEffect(() => {
    if (!token) return
    const refresh = async () => {
      try {
        const [statusData, tradesData, signalsData] = await Promise.all([
          apiFetch('/api/status'),
          apiFetch('/api/trades'),
          apiFetch('/api/signals')
        ])
        setStatus(statusData)
        setTrades(tradesData.slice(0, 10))
        setSignals(signalsData.slice(0, 5))
      } catch (err) {
        console.error('Failed to refresh dashboard:', err)
      }
    }
    refresh()
    const interval = setInterval(refresh, 10000)
    return () => clearInterval(interval)
  }, [token])

  if (!token) {
    return (
      <div className="app">
        <header className="header">
          <h1>🚀 Binance Trading Bot</h1>
        </header>
        <LoginForm onLogin={setToken} />
      </div>
    )
  }

  if (!status) {
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
        <div className={`status-badge ${status.dry_run ? 'dry-run' : 'live'}`}>
          {status.dry_run ? '🧪 DRY RUN' : '✅ LIVE'}
        </div>
        <button onClick={logout} className="auth-button logout-button">Abmelden</button>
      </header>

      <div className="dashboard">
        <StatusCard status={status} />
        <SignalsList signals={signals} />
        <TradesTable trades={trades} />
        <ConfigPanel />
      </div>
    </div>
  )
}

export default App
