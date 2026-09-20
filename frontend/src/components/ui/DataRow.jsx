import { CiteBadge } from './Tag';
import { hasData, initials, isHistoricalLeader, val } from '../../utils/data';
import { Tag } from './Tag';

// "Label: value  [source] [confidence]" — renders nothing when the value is missing.
// `text` overrides how the value is read from `field` (used for risk lists).
export function IntelRow({ label, field, text: textOverride }) {
  const isObject = field && typeof field === 'object' && !Array.isArray(field);
  const text = textOverride ?? (isObject ? val(field) : typeof field === 'string' ? field : val(field));
  if (!hasData(text)) return null;
  return (
    <div className="data-row">
      <span className="data-row__label">{label}:</span> {text}
      {isObject && <CiteBadge field={field} />}
    </div>
  );
}

export function Person({ name, role, historical = false }) {
  return (
    <div className="person">
      <div className="avatar" aria-hidden="true">
        {initials(name)}
      </div>
      <div style={{ minWidth: 0 }}>
        <div className="person__name">{name || 'Unknown'}</div>
        {role && <div className="person__role">{role}</div>}
        {historical && <Tag tone="neutral">Historical — not current operating exec</Tag>}
      </div>
    </div>
  );
}

export function LeaderPerson({ leader }) {
  return (
    <Person
      name={leader.name}
      role={leader.role || leader.title || ''}
      historical={isHistoricalLeader(leader)}
    />
  );
}
