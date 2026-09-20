import { Tag } from '../ui';

const REVIEW_TONE = { approved: 'green', pending: 'amber', rejected: 'red', duplicate: 'neutral' };
const HEALTH = {
  healthy: ['green', 'Healthy'], degraded: ['amber', 'Degraded'], failing: ['red', 'Failing'], stale: ['amber', 'Stale'],
  never_run: ['neutral', 'Never run'], not_configured: ['neutral', 'Not configured'], manual: ['neutral', 'Manual'],
};
const RUN_TONE = { success: 'green', partial: 'amber', failed: 'red', running: 'neutral' };

export const ReviewBadge = ({ value }) => <Tag tone={REVIEW_TONE[value] || 'neutral'}>{value || 'unknown'}</Tag>;
export const HealthBadge = ({ value }) => {
  const [tone, label] = HEALTH[value] || ['neutral', value];
  return <Tag tone={tone}>{label}</Tag>;
};
export const RunBadge = ({ value }) => <Tag tone={RUN_TONE[value] || 'neutral'}>{value}</Tag>;

export function formatDateTime(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

export function Field({ label, htmlFor, hint, required, children, wide }) {
  return (
    <div className={`adm-field ${wide ? 'adm-field--wide' : ''}`}>
      <label className="form-label" htmlFor={htmlFor}>
        {label}
        {required && <span className="adm-req" aria-hidden="true"> *</span>}
      </label>
      {children}
      {hint && <p className="form-hint">{hint}</p>}
    </div>
  );
}
