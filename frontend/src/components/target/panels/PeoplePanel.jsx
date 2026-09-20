import { IntelRow, LeaderPerson } from '../../ui';
import { asArray, ensureUrl, val } from '../../../utils/data';

const confidenceTone = (c) => ({ high: 'high', medium: 'medium', med: 'medium', low: 'low' })[String(c || 'medium').toLowerCase()] || '';

export default function PeoplePanel({ report }) {
  const co = report.company_profile || {};
  const emp = report.employee_insights || {};
  const leaders = asArray(report.leadership_team);
  const hiring = asArray(report.hiring_signals).filter((h) => h && h.role);

  return (
    <>
      <h4 className="subhead">Workforce stats</h4>
      <IntelRow label="Total employees" field={emp.total_employees || co.employee_count || co.employees} />
      <IntelRow label="Hiring trend" field={emp.hiring_trend} />
      <IntelRow label="Remote policy" field={emp.remote_policy} />
      <IntelRow label="Glassdoor rating" field={emp.glassdoor_rating} />

      <h4 className="subhead">Current leadership</h4>
      {leaders.length ? (
        leaders.map((l, i) => (
          <div className="data-row" key={`${l.name}-${i}`}>
            <LeaderPerson leader={l} />
            <div style={{ marginTop: 6 }}>
              {l.din && <span className="cite-badge">DIN {l.din}</span>}
              <span className="cite-badge" style={{ marginLeft: l.din ? 6 : 0 }}>
                {l.source || 'Public source'}
              </span>
              <span className={`cite-badge cite-badge--${confidenceTone(l.confidence)}`}>● {l.confidence || 'Medium'}</span>
            </div>
            {l.background && <p className="text-xs muted" style={{ marginTop: 6 }}>{l.background}</p>}
          </div>
        ))
      ) : (
        <p className="field-value muted">No public leadership found.</p>
      )}

      <h4 className="subhead">Verified hiring</h4>
      {hiring.length ? (
        <>
          <p className="text-sm muted" style={{ marginBottom: 8 }}>
            Official careers, LinkedIn, Naukri, Indeed and company ATS pages. Click a source to open it.
          </p>
          <ul className="list-plain">
            {hiring.map((h, i) => (
              <li className="list-split" key={`${h.role}-${i}`}>
                <span style={{ fontWeight: 500 }}>{h.role}</span>
                <span className="text-xs muted">
                  {h.platform || 'Official'}
                  {h.source_url && (
                    <>
                      {' · '}
                      <a href={ensureUrl(h.source_url)} target="_blank" rel="noopener noreferrer">
                        source
                      </a>
                    </>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </>
      ) : (
        <p className="field-value muted">No public hiring found.</p>
      )}

      <h4 className="subhead">Culture</h4>
      <p className="field-value" style={{ fontStyle: 'italic' }}>
        {val(emp.culture_summary) || 'Limited public culture reviews found'}
      </p>
    </>
  );
}
