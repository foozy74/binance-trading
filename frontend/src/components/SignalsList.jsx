export default function SignalsList({ signals }) {
  if (!signals || signals.length === 0) {
    return (
      <div className="glass-card">
        <h2>📈 Recent Signals</h2>
        <p style={{ color: '#a0a0b0' }}>No signals available. Enter API key to load.</p>
      </div>
    )
  }

  return (
    <div className="glass-card">
      <h2>📈 Recent Signals</h2>
      <div className="table-container">
        <table>
          <thead>
            <tr>
              <th>Signal</th>
              <th>Strategy</th>
              <th>Confidence</th>
              <th>Time</th>
            </tr>
          </thead>
          <tbody>
            {signals.map((signal) => (
              <tr key={signal.id}>
                <td>
                  <span className={`signal-badge ${signal.signal.toLowerCase()}`}>
                    {signal.signal}
                  </span>
                </td>
                <td>{signal.strategy}</td>
                <td>{signal.confidence ? `${(signal.confidence * 100).toFixed(0)}%` : '-'}</td>
                <td>{new Date(signal.created_at).toLocaleTimeString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
