import { IntelRow, LeaderPerson } from '../../ui';
import { asArray, ensureUrl, val } from '../../../utils/data';

const confidenceTone = (c) => ({ high: 'high', medium: 'medium', med: 'medium', low: 'low' })[String(c || 'medium').toLowerCase()] || '';
const verificationLabel = (leader) =>
  leader?.verification_status === 'model-knowledge-reviewed'
    ? 'AI knowledge reviewed'
    : leader?.verification_status === 'search-snippet-supported'
      ? 'Search snippet only - page not fetched'
      : leader?.verification_status === 'evidence-verified'
        ? 'Evidence verified'
        : '';

export default function PeoplePanel({ report }) {
  const co = report.company_profile || {};
  const emp = report.employee_insights || {};
  const leaders = asArray(report.leadership_team)
    .filter((leader) => leader?.verification_status !== 'model-knowledge-reviewed');
  const hiring = asArray(report.hiring_signals).filter((h) => h && h.role);
  const ai = report.ai_enrichment || {};
  const profileReviewComplete = ['complete', 'complete_no_new_facts', 'ai_profile_used'].includes(ai.status);

  return (
    <>
      {ai.status && ai.status !== 'disabled' && (
        <div className="callout ai-profile-callout">
          <strong>Public-source profile review</strong>
          <p className="text-sm muted" style={{ marginTop: 6 }}>
            {profileReviewComplete
              ? 'Retrieved public records and search results were reviewed for this company.'
              : 'The public-source review did not complete. Use the links beside each fact to inspect its source.'}
          </p>
          {profileReviewComplete && (
            <p className="text-xs muted" style={{ marginTop: 6 }}>
              Evidence review: {ai.judge_score || 0}/100 - {ai.evidence_count || 0} public evidence records considered.
            </p>
          )}
          {ai.business_fields_added > 0 && (
            <p className="text-xs muted" style={{ marginTop: 6 }}>
              The review supplemented {ai.business_fields_added} missing stable profile field(s). Email addresses and phone numbers are retained only when found in the linked public sources.
            </p>
          )}
        </div>
      )}
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
              {verificationLabel(l) && <span className="cite-badge">{verificationLabel(l)}</span>}
              <span className={`cite-badge cite-badge--${confidenceTone(l.confidence)}`}>● {l.confidence || 'Medium'}</span>
            </div>
            {l.background && <p className="text-xs muted" style={{ marginTop: 6 }}>{l.background}</p>}
            {asArray(l.source_urls).filter((u) => /^https?:\/\//i.test(String(u))).slice(0, 2).map((u) => (
              <a className="text-xs" href={u} target="_blank" rel="noopener noreferrer" key={u} style={{ marginRight: 8 }}>
                Source
              </a>
            ))}
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
