import { Link2 } from 'lucide-react';
import { Card, CardHeader } from '../ui';
import { citeHref } from '../../utils/data';

export default function SourcesCard({ citations }) {
  if (!citations.length) return null;
  return (
    <Card id="sources" style={{ scrollMarginTop: 90 }}>
      <CardHeader icon={Link2} title="Sources & verified references" />
      {citations.map((c, i) => {
        const href = citeHref(c);
        return (
          <div className="citation-item" key={`${href}-${i}`}>
            <span className="citation-item__num">{i + 1}</span>
            <div style={{ minWidth: 0 }}>
              <a className="citation-item__title" href={href} target="_blank" rel="noopener noreferrer">
                {c.title || c.domain || 'Source'}
              </a>
              <div className="citation-item__meta">
                {c.domain || href}
                {c.category ? ` · ${c.category}` : ''}
              </div>
            </div>
          </div>
        );
      })}
    </Card>
  );
}
