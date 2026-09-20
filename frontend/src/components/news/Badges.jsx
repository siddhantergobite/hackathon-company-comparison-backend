import { Link } from 'react-router-dom';
import { Flame, Layers, Siren } from 'lucide-react';
import { CATEGORY_HUE, timeAgo } from '../../utils/news';

export function SourceBadge({ name, time, count }) {
  return (
    <span className="nw-source">
      <span className="nw-source__name">{name || 'Unknown source'}</span>
      {time && (
        <>
          <span aria-hidden="true">·</span>
          <time dateTime={time}>{timeAgo(time)}</time>
        </>
      )}
      {count > 1 && (
        <span className="nw-coverage" title={`Covered by ${count} sources`}>
          <Layers size={12} aria-hidden="true" /> {count}
        </span>
      )}
    </span>
  );
}

export function CategoryBadge({ slug, name, categories = {} }) {
  const label = name || categories[slug]?.name || (slug ? slug.replace(/-/g, ' ') : '');
  if (!label) return null;
  return (
    <span className="nw-cat" style={{ '--hue': CATEGORY_HUE[slug] ?? 220 }}>
      {label}
    </span>
  );
}

export function TopicBadge({ topic, asLink = true }) {
  if (!asLink) return <span className="nw-topic">{topic}</span>;
  return (
    <Link className="nw-topic" to={`/news?topic=${encodeURIComponent(topic)}`}>
      {topic}
    </Link>
  );
}

export function BreakingPill() {
  return (
    <span className="nw-pill nw-pill--breaking">
      <Siren size={12} aria-hidden="true" /> Breaking
    </span>
  );
}

export function TrendingPill() {
  return (
    <span className="nw-pill nw-pill--trending">
      <Flame size={12} aria-hidden="true" /> Trending
    </span>
  );
}
