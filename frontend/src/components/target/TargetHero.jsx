import { citeHref } from '../../utils/data';

const MAX_STACK = 4;

export function TargetHero({ view }) {
  return (
    <div className="hero">
      <h2 className="hero__title">{view.heroTitle}</h2>
      {view.heroSub && <div className="hero__sub">{view.heroSub}</div>}
      {view.heroSummary && <p className="hero__summary">{view.heroSummary}</p>}
    </div>
  );
}

export function SourcesBar({ citations, count }) {
  if (!citations.length) return null;
  const shown = citations.slice(0, MAX_STACK);
  return (
    <div className="sources-bar">
      <div className="favicon-stack" style={{ width: 26 + Math.max(0, shown.length - 1) * 16 }}>
        {shown.map((c, i) => {
          const label = c.title || c.domain || 'Source';
          const favicon =
            c.favicon || `https://www.google.com/s2/favicons?domain=${encodeURIComponent(c.domain || '')}&sz=64`;
          return (
            <a
              key={`${label}-${i}`}
              href={citeHref(c)}
              target="_blank"
              rel="noopener noreferrer"
              title={label}
              style={{ left: i * 16 }}
            >
              <img
                src={favicon}
                alt={c.domain || label}
                onError={(e) => {
                  e.currentTarget.style.visibility = 'hidden';
                }}
              />
            </a>
          );
        })}
      </div>
      <a href="#sources" className="text-sm" style={{ fontWeight: 600 }}>
        {count} source{count !== 1 ? 's' : ''}
      </a>
      <span className="text-sm muted">Every fact is traced to a public source.</span>
    </div>
  );
}
