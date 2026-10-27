export default function TradesTable({ trades }) {
  if (!trades || trades.length === 0) {
    return (
      <div className="glass-card">
        <h2>💼 Recent Trades</h2>
        <p style={{ color: '#a0a0b0' }}>No trades available. Enter API key to load.</p>
      </div>
    )
  }

  return (
    <div className="glass-card" style={{ gridColumn: 'span 2' }}>
      <h2>💼 Recent Trades</h2>
      <div className="table-container">
        <table>
          <thead>
            <tr>
              <th>Time</th>
              <th>Side</th>
              <th>Symbol</th>
              <th>Amount</th>
              <th>Price</th>
              <th>Value (USDT)</th>
              <th>Mode</th>
            </tr>
          </thead>
          <tbody>
            {trades.map((trade) => (
              <tr key={trade.id}>
                <td>{new Date(trade.created_at).toLocaleString()}</td>
                <td>
                  <span className={`signal-badge ${trade.side}`}>
                    {trade.side.toUpperCase()}
                  </span>
                </td>
                <td>{trade.symbol}</td>
                <td>{trade.amount.toFixed(6)}</td>
                <td>${trade.price.toFixed(2)}</td>
                <td>${trade.usdt_value.toFixed(2)}</td>
                <td>{trade.is_dry_run ? '🧪 Dry' : '✅ Live'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
