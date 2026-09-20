import { IntelRow } from '../../ui';
import { hasData, riskText } from '../../../utils/data';

const RISK_FIELDS = [
  ['Overall risk level', 'overall_risk_level'],
  ['Regulatory risks', 'regulatory_risks'],
  ['Competitive risks', 'competitive_risks'],
  ['Operational risks', 'operational_risks'],
  ['Reputational risks', 'reputational_risks'],
];

export default function RiskPanel({ report }) {
  const fin = report.financial_data || {};
  const risk = report.risk_assessment || {};
  const rows = RISK_FIELDS.map(([label, key]) => ({ label, key, field: risk[key], text: riskText(risk[key]) })).filter(
    (r) => hasData(r.text),
  );

  return (
    <>
      <h4 className="subhead">Financial intelligence</h4>
      <IntelRow label="Revenue estimate" field={fin.revenue_estimate} />
      <IntelRow label="Funding" field={fin.funding_status || fin.total_funding} />

      <h4 className="subhead">Risk assessment</h4>
      {rows.length ? (
        rows.map((r) => <IntelRow key={r.key} label={r.label} field={Array.isArray(r.field) ? null : r.field} text={r.text} />)
      ) : (
        <p className="field-value muted">—</p>
      )}
    </>
  );
}
