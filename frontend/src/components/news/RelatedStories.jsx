import { Link } from 'react-router-dom';
import { ExternalLink, Layers } from 'lucide-react';
import { Card, CardHeader } from '../ui';
import { SourceBadge } from './Badges';
import { NewsImage } from './NewsCard';
import { safeHref, timeAgo } from '../../utils/news';

// Every outlet's own article about this story, each one linking out to the publisher.
export function CoverageList({ articles, currentId }) {
  if (!articles?.length) return null;
  return (
    <Card as="section" aria-labelledby="coverage-h">
      <CardHeader icon={Layers} title={`Related coverage (${articles.length} ${articles.length === 1 ? 'source' : 'sources'})`} />
      <ul className="nw-coverage-list" id="coverage-h">
        {articles.map((a) => (
          <li key={a.id} className={a.id === currentId ? 'is-current' : ''}>
            <div className="nw-coverage-list__main">
              <strong className="nw-coverage-list__source">{a.source?.name}</strong>
              <span className="muted text-xs">{timeAgo(a.published_at)}</span>
              <div className="nw-coverage-list__title">
                {a.id === currentId ? a.title : <Link to={`/news/${a.id}`} className="nw-link">{a.title}</Link>}
              </div>
            </div>
            {safeHref(a.url) && (
              <a className="nw-ext" href={safeHref(a.url)} target="_blank" rel="noopener noreferrer" aria-label={`Read at ${a.source?.name} (opens in a new tab)`}>
                Read at {a.source?.name} <ExternalLink size={13} aria-hidden="true" />
              </a>
            )}
          </li>
        ))}
      </ul>
    </Card>
  );
}

export function MoreLikeThis({ articles }) {
  if (!articles?.length) return null;
  return (
    <section aria-labelledby="more-h">
      <div className="nw-section-head"><h2 id="more-h">More like this</h2></div>
      <div className="nw-morelike">
        {articles.map((a) => (
          <article key={a.id} className="nw-compact">
            <NewsImage src={a.image_url} category={a.category} className="nw-compact__img" size={20} />
            <div className="nw-compact__body">
              <h3 className="nw-compact__title"><Link to={`/news/${a.id}`} className="nw-link">{a.title}</Link></h3>
              <SourceBadge name={a.source?.name} time={a.published_at} />
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
