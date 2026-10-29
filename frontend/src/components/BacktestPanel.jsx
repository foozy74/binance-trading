import { useState } from 'react'
import { apiFetch } from '../api'

const STRATEGIES = {
  '': 'Alle Strategien',
  obv_vwap: 'OBV + VWAP',
  rsi_divergence: 'RSI Divergence',
  macd_crossover: 'MACD Crossover',
  multi_signal: 'Multi Signal'
}

const pct = (value) => `${(value * 100).toFixed(2)}%`
const tone = (value) => (value >= 0 ? 'positive' : 'negative')

// Prozent-Eingabe ("2" = 2 %) in Anteil umrechnen; leer = kein SL/TP
const fraction = (text) => (text === '' ? null : Number(text) / 100)

export default function BacktestPanel() {
  const [form, setForm] = useState({ strategy: '', candles: 2000, stopLoss: '', takeProfit: '' })
  const [result, setResult] = useState(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState('')

  const change = (key) => (e) => setForm({ ...form, [key]: e.target.value })

  const run = async (e) => {
    e.preventDefault()
    setRunning(true)
    setError('')
    try {
      setResult(await apiFetch('/api/backtest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          strategy: form.strategy || null,
          candles: Number(form.candles),
          stop_loss: fraction(form.stopLoss),
          take_profit: fraction(form.takeProfit)
        })
      }))
    } catch (err) {
      setError(err.message || 'Backtest fehlgeschlagen')
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="glass-card" style={{ gridColumn: 'span 2' }}>
      <h2>🧪 Backtest</h2>
      <form onSubmit={run} className="backtest-form">
        <label>Strategie
          <select value={form.strategy} onChange={change('strategy')} className="auth-input">
            {Object.entries(STRATEGIES).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
          </select>
        </label>
        <label>Kerzen (1h)
          <input type="number" min="200" max="5000" required value={form.candles}
            onChange={change('candles')} className="auth-input" />
        </label>
        <label>Stop-Loss %
          <input type="number" min="0.1" max="99" step="0.1" placeholder="aus" value={form.stopLoss}
            onChange={change('stopLoss')} className="auth-input" />
        </label>
        <label>Take-Profit %
          <input type="number" min="0.1" max="99" step="0.1" placeholder="aus" value={form.takeProfit}
            onChange={change('takeProfit')} className="auth-input" />
        </label>
        <button type="submit" className="auth-button" disabled={running}>
          {running ? 'Läuft …' : 'Starten'}
        </button>
      </form>

      {error && <p className="login-error">{error}</p>}

      {result && (
        <div className="table-container">
          <p className="stat-label">
            {result.symbol}, {result.candles} Kerzen {new Date(result.start).toLocaleString()} –{' '}
            {new Date(result.end).toLocaleString()} · Buy &amp; Hold{' '}
            <span className={`stat-value ${tone(result.buy_hold)}`}>{pct(result.buy_hold)}</span>
          </p>
          <table>
            <thead>
              <tr><th>Strategie</th><th>Rendite</th><th>Max-Drawdown</th><th>Trades</th><th>Trefferquote</th></tr>
            </thead>
            <tbody>
              {result.results.map((r) => (
                <tr key={r.strategy}>
                  <td>{STRATEGIES[r.strategy] || r.strategy}</td>
                  <td className={`stat-value ${tone(r.total_return)}`}>{pct(r.total_return)}</td>
                  <td className="stat-value negative">{pct(r.max_drawdown)}</td>
                  <td>{r.trades}</td>
                  <td>{(r.win_rate * 100).toFixed(0)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
