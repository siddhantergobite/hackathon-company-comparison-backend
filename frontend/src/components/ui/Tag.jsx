import { hasData } from '../../utils/data';

export function Tag({ tone, children, className = '' }) {
  return <span className={['tag', tone ? `tag--${tone}` : '', className].filter(Boolean).join(' ')}>{children}</span>;
}

export function TagList({ children }) {
  return <div className="tag-list">{children}</div>;
}

const CONFIDENCE_TONE = { high: 'high', medium: 'medium', med: 'medium', low: 'low' };

// Small "source · confidence" chips shown next to researched facts.
export function CiteBadge({ field }) {
  if (!field || typeof field !== 'object' || Array.isArray(field)) return null;
  const source = field.source || '';
  const confidence = String(field.confidence || '');
  const tone = CONFIDENCE_TONE[confidence.toLowerCase()] || '';
  return (
    <>
      {source && hasData(source) && <span className="cite-badge">{String(source)}</span>}
      {confidence && <span className={`cite-badge cite-badge--${tone}`}>● {confidence}</span>}
    </>
  );
}
