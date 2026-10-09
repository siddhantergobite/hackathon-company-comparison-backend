import { CiteBadge, IntelRow } from '../../ui';
import { hasData } from '../../../utils/data';

const RISK_FIELDS = [
  ['Regulatory risks', 'regulatory_risks'],
  ['Competitive risks', 'competitive_risks'],
  ['Operational risks', 'operational_risks'],
  ['Reputational risks', 'reputational_risks'],
];

const safeHttpUrl = (value) => /^https?:\/\//i.test(String(value || '').trim()) ? String(value).trim() : '';

export default function RiskPanel({ report }) {
  const fin = report.financial_data || {};
  const risk = report.risk_assessment || {};

  return (
    <>
      <h4 className="subhead">Financial intelligence</h4>
      <IntelRow label="Revenue estimate" field={fin.revenue_estimate} />
      <IntelRow label="Funding status" field={fin.funding_status || fin.funding_stage} />
      <IntelRow label="Total funding" field={fin.total_funding} />
      <IntelRow label="Profitability status" field={fin.profitability_status} />

      <h4 className="subhead">Risk assessment</h4>
      <IntelRow label="Overall risk level" field={risk.overall_risk_level || 'Undetermined'} />
      {risk.overall_risk_level === 'Undetermined' && (
        <p className="text-xs muted">A company-level risk rating was not assigned because the retrieved evidence did not support one.</p>
      )}
      {RISK_FIELDS.map(([label, key]) => {
        const items = Array.isArray(risk[key]) ? risk[key] : risk[key] ? [risk[key]] : [];
        return (
          <div className="data-row" key={key}>
            <div className="data-row__label">{label}:</div>
            {items.length ? items.map((item, i) => {
              const row = typeof item === 'string' ? { risk: item } : item;
              const text = row?.risk || row?.point || row?.value || '';
              if (!hasData(text)) return null;
              const sourceUrl = safeHttpUrl(row.source_url || row.evidence_url);
              return (
                <div key={`${text}-${i}`} style={{ margin: '4px 0 8px' }}>
                  <span>{text}</span>
                  <CiteBadge field={row} />
                  {row.basis === 'analysis' && <span className="cite-badge cite-badge--medium">Analysis</span>}
                  {sourceUrl && <a className="text-xs" href={sourceUrl} target="_blank" rel="noopener noreferrer">Source</a>}
                </div>
              );
            }) : <span className="text-sm muted">No company-specific risk was verified in the sources checked.</span>}
          </div>
        );
      })}
    </>
  );
}
