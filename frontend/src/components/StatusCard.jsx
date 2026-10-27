export default function StatusCard({ status }) {
  if (!status) return null

  return (
    <div className="glass-card">
      <h2>📊 Bot Status</h2>
      <div className="stat-item">
        <span className="stat-label">Status</span>
        <span className="stat-value positive">{status.status}</span>
      </div>
      <div className="stat-item">
        <span className="stat-label">Strategy</span>
        <span className="stat-value">{status.active_strategy}</span>
      </div>
      <div className="stat-item">
        <span className="stat-label">Symbol</span>
        <span className="stat-value">{status.symbol}</span>
      </div>
      <div className="stat-item">
        <span className="stat-label">Dry Run</span>
        <span className={`stat-value ${status.dry_run ? 'positive' : 'negative'}`}>
          {status.dry_run ? 'Yes' : 'No'}
        </span>
      </div>
      {status.last_signal && (
        <div className="stat-item">
          <span className="stat-label">Last Signal</span>
          <span className={`stat-value ${status.last_signal === 'BUY' ? 'positive' : status.last_signal === 'SELL' ? 'negative' : ''}`}>
            {status.last_signal}
          </span>
        </div>
      )}
    </div>
  )
}
