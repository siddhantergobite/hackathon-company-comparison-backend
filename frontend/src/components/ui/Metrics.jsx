function toneFor(value) {
  if (value >= 70) return 'var(--success)';
  if (value >= 40) return 'var(--warning)';
  return 'var(--danger)';
}

export function KpiGrid({ items }) {
  if (!items.length) return null;
  return (
    <div className="kpi-grid">
      {items.map(([label, value]) => (
        <div className={`kpi ${String(value).length > 26 ? 'kpi--wide' : ''}`} key={label}>
          <div className="kpi__label">{label}</div>
          <div className="kpi__value">{String(value)}</div>
        </div>
      ))}
    </div>
  );
}

// Circular gauge for a 0–100 score; shows an em dash when the score is unknown.
export function ScoreRing({ value, size = 76, stroke = 8, label }) {
  const known = typeof value === 'number' && Number.isFinite(value);
  const r = (size - stroke) / 2;
  const circumference = 2 * Math.PI * r;
  const offset = known ? circumference * (1 - value / 100) : circumference;
  return (
    <div className="score-ring" style={{ width: size, height: size }} role="img" aria-label={label || `Score ${known ? value : 'unavailable'}`}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true">
        <circle className="score-ring__track" cx={size / 2} cy={size / 2} r={r} fill="none" strokeWidth={stroke} />
        {known && (
          <circle
            className="score-ring__value"
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            strokeWidth={stroke}
            strokeLinecap="round"
            stroke={toneFor(value)}
            strokeDasharray={circumference}
            strokeDashoffset={offset}
          />
        )}
      </svg>
      <span className="score-ring__label" style={{ fontSize: size * 0.3 }}>
        {known ? value : '—'}
      </span>
    </div>
  );
}

export function Meter({ label, value }) {
  const known = typeof value === 'number';
  return (
    <div className="meter">
      <div className="meter__top">
        <span>{label}</span>
        <strong>{known ? `${value}/100` : '—'}</strong>
      </div>
      <div className="meter__bar" role="presentation">
        {known && <span style={{ width: `${value}%`, background: toneFor(value) }} />}
      </div>
    </div>
  );
}
