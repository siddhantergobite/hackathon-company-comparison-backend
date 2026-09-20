import { CiteBadge } from '../../ui';
import { asArray, hasData, pointOf } from '../../../utils/data';

function SwotBox({ tone, title, items }) {
  const rows = asArray(items)
    .map((item) => ({ item, text: pointOf(item) }))
    .filter(({ text }) => hasData(text));
  return (
    <div className={`swot-box swot-box--${tone}`}>
      <h5>{title}</h5>
      <ul>
        {rows.length ? (
          rows.map(({ item, text }, i) => (
            <li key={`${text}-${i}`}>
              {text}
              {typeof item === 'object' && <CiteBadge field={item} />}
            </li>
          ))
        ) : (
          <li>—</li>
        )}
      </ul>
    </div>
  );
}

export default function SwotPanel({ report }) {
  const swot = report.swot_analysis || {};
  return (
    <div className="swot-grid">
      <SwotBox tone="s" title="Strengths" items={swot.strengths} />
      <SwotBox tone="w" title="Weaknesses" items={swot.weaknesses} />
      <SwotBox tone="o" title="Opportunities" items={swot.opportunities} />
      <SwotBox tone="t" title="Threats" items={swot.threats} />
    </div>
  );
}
