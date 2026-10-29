import { useState } from 'react'
import { apiFetch, STRATEGIES } from '../api'

export default function ConfigPanel() {
  const [config, setConfig] = useState(null)
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')

  const fetchConfig = async () => {
    setLoading(true)
    try {
      setConfig(await apiFetch('/api/config'))
    } catch (err) {
      setMessage('Failed to load config')
    } finally {
      setLoading(false)
    }
  }

  const updateConfig = async (key, value) => {
    try {
      await apiFetch('/api/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ [key]: value })
      })
      setMessage('Config updated!')
      setTimeout(() => setMessage(''), 3000)
      fetchConfig()
    } catch (err) {
      setMessage('Failed to update config')
    }
  }

  return (
    <div className="glass-card">
      <h2>⚙️ Configuration</h2>
      <button onClick={fetchConfig} className="auth-button" style={{ marginBottom: '15px' }}>
        {loading ? 'Loading...' : 'Load Config'}
      </button>
      
      {message && (
        <div style={{ 
          padding: '10px', 
          borderRadius: '8px', 
          background: message.includes('Failed') ? 'rgba(255,71,87,0.2)' : 'rgba(0,212,170,0.2)',
          marginBottom: '15px'
        }}>
          {message}
        </div>
      )}

      {config && (
        <div>
          <div className="stat-item">
            <span className="stat-label">Active Strategy</span>
            <select
              value={config.active_strategy}
              onChange={(e) => updateConfig('active_strategy', e.target.value)}
              style={{
                padding: '8px',
                borderRadius: '8px',
                background: 'rgba(255,255,255,0.1)',
                border: '1px solid rgba(255,255,255,0.2)',
                color: 'white'
              }}
            >
              {Object.entries(STRATEGIES).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
            </select>
          </div>
          <div className="stat-item">
            <span className="stat-label">Trade Percentage</span>
            <span className="stat-value">{(config.trade_percentage * 100).toFixed(0)}%</span>
          </div>
          <div className="stat-item">
            <span className="stat-label">Trailing Stop</span>
            <span className="stat-value">{(config.trailing_stop_percent * 100).toFixed(0)}%</span>
          </div>
          <div className="stat-item">
            <span className="stat-label">Take Profit</span>
            <span className="stat-value">{(config.take_profit_percent * 100).toFixed(0)}%</span>
          </div>
        </div>
      )}
    </div>
  )
}
