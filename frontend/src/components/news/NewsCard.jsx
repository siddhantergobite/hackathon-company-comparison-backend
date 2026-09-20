import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Newspaper } from 'lucide-react';
import { BreakingPill, CategoryBadge, SourceBadge, TrendingPill } from './Badges';
import { CATEGORY_HUE, isTrending, sourceCount } from '../../utils/news';

// Photo when there is one; otherwise a soft gradient keyed to the category.
export function NewsImage({ src, category, className = '', size = 30 }) {
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [src]);
  if (!src || failed) {
    return (
      <div className={`nw-img nw-img--fallback ${className}`} style={{ '--hue': CATEGORY_HUE[category] ?? 220 }} aria-hidden="true">
        <Newspaper size={size} />
      </div>
    );
  }
  return <img className={`nw-img ${className}`} src={src} alt="" loading="lazy" referrerPolicy="no-referrer" onError={() => setFailed(true)} />;
}

const teaser = (a) => a.summary || a.description || '';

/** variant: "default" (card) | "feature" (hero) | "compact" (thumbnail row) */
export default function NewsCard({ article: a, variant = 'default', categories }) {
  const count = sourceCount(a);
  const to = `/news/${a.id}`;

  if (variant === 'compact') {
    return (
      <article className="nw-compact">
        <NewsImage src={a.image_url} category={a.category} className="nw-compact__img" size={20} />
        <div className="nw-compact__body">
          <CategoryBadge slug={a.category} categories={categories} />
          <h3 className="nw-compact__title">
            <Link to={to} className="nw-link">{a.title}</Link>
          </h3>
          <SourceBadge name={a.source?.name} time={a.last_activity_at || a.published_at} count={count} />
        </div>
      </article>
    );
  }

  if (variant === 'feature') {
    return (
      <article className="nw-feature">
        <NewsImage src={a.image_url} category={a.category} className="nw-feature__img" size={54} />
        <div className="nw-feature__shade" />
        <div className="nw-feature__body">
          <div className="nw-feature__badges">
            {a.is_breaking && <BreakingPill />}
            {isTrending(a) && !a.is_breaking && <TrendingPill />}
            <CategoryBadge slug={a.category} categories={categories} />
          </div>
          <h2 className="nw-feature__title">
            <Link to={to} className="nw-link">{a.title}</Link>
          </h2>
          {teaser(a) && <p className="nw-feature__summary">{teaser(a)}</p>}
          <div className="nw-feature__foot">
            <SourceBadge name={a.source?.name} time={a.last_activity_at || a.published_at} count={count} />
            <span className="nw-feature__cta" aria-hidden="true">Read story →</span>
          </div>
        </div>
      </article>
    );
  }

  return (
    <article className="nw-card">
      <div className="nw-card__media">
        <NewsImage src={a.image_url} category={a.category} />
        <div className="nw-card__pills">
          {a.is_breaking && <BreakingPill />}
          {isTrending(a) && !a.is_breaking && <TrendingPill />}
        </div>
      </div>
      <div className="nw-card__body">
        <CategoryBadge slug={a.category} categories={categories} />
        <h3 className="nw-card__title">
          <Link to={to} className="nw-link">{a.title}</Link>
        </h3>
        {teaser(a) && <p className="nw-card__summary">{teaser(a)}</p>}
        <div className="nw-card__foot">
          <SourceBadge name={a.source?.name} time={a.last_activity_at || a.published_at} count={count} />
        </div>
        {count > 1 && (
          <div className="nw-card__covered" title={(a.coverage?.sources || []).join(', ')}>
            Covered by {count} sources · {(a.coverage?.sources || []).slice(0, 3).join(' · ')}{(a.coverage?.sources || []).length > 3 ? ' …' : ''}
          </div>
        )}
      </div>
    </article>
  );
}

export function NewsCardSkeleton({ variant = 'default' }) {
  if (variant === 'compact') {
    return (
      <div className="nw-compact" aria-hidden="true">
        <div className="skeleton nw-compact__img" />
        <div className="nw-compact__body">
          <div className="skeleton skeleton--line" style={{ width: '30%' }} />
          <div className="skeleton skeleton--line" />
          <div className="skeleton skeleton--line" style={{ width: '60%' }} />
        </div>
      </div>
    );
  }
  return (
    <div className="nw-card" aria-hidden="true">
      <div className="nw-card__media skeleton" />
      <div className="nw-card__body">
        <div className="skeleton skeleton--line" style={{ width: '25%' }} />
        <div className="skeleton skeleton--title" />
        <div className="skeleton skeleton--line" />
        <div className="skeleton skeleton--line" style={{ width: '85%' }} />
        <div className="skeleton skeleton--line" style={{ width: '45%', marginTop: 10 }} />
      </div>
    </div>
  );
}
