import { Link } from 'react-router-dom';
import { ChevronRight, Flame, Radio, TrendingUp } from 'lucide-react';
import { Banner, Card, EmptyState } from '../ui';
import Button from '../ui/Button';
import NewsCard, { NewsCardSkeleton } from './NewsCard';
import { SourceBadge } from './Badges';
import { sourceCount, timeAgo } from '../../utils/news';

// ---------------------------------------------------------------- grid + list
export function NewsGrid({ articles, categories, loading = false, skeletons = 6 }) {
  if (loading && !articles.length) {
    return (
      <div className="nw-grid">
        {Array.from({ length: skeletons }, (_, i) => <NewsCardSkeleton key={i} />)}
      </div>
    );
  }
  return (
    <div className="nw-grid">
      {articles.map((a) => <NewsCard key={a.id} article={a} categories={categories} />)}
    </div>
  );
}

export function NewsList({ articles, categories }) {
  return (
    <div className="nw-list">
      {articles.map((a) => <NewsCard key={a.id} article={a} variant="compact" categories={categories} />)}
    </div>
  );
}

// -------------------------------------------------------------------- top stories
export function TopStories({ articles, loading, categories }) {
  if (loading && !articles?.length) {
    return (
      <section className="nw-top" aria-label="Top stories">
        <div className="nw-top__lead skeleton" style={{ minHeight: 360 }} />
        <div className="nw-top__side">{Array.from({ length: 3 }, (_, i) => <NewsCardSkeleton key={i} variant="compact" />)}</div>
      </section>
    );
  }
  if (!articles?.length) return null;
  const [lead, ...rest] = articles;
  return (
    <section aria-labelledby="top-stories-h">
      <div className="nw-section-head">
        <h2 id="top-stories-h"><Flame size={18} aria-hidden="true" /> Top stories</h2>
      </div>
      <div className="nw-top">
        <NewsCard article={lead} variant="feature" categories={categories} />
        <div className="nw-top__side">
          {rest.slice(0, 4).map((a) => <NewsCard key={a.id} article={a} variant="compact" categories={categories} />)}
        </div>
      </div>
    </section>
  );
}

// ----------------------------------------------------------------- trending now
export function TrendingStories({ articles, loading }) {
  return (
    <Card className="nw-trending" as="aside" aria-labelledby="trending-h">
      <div className="nw-section-head nw-section-head--tight">
        <h2 id="trending-h"><TrendingUp size={18} aria-hidden="true" /> Trending now</h2>
      </div>
      {loading && !articles?.length ? (
        <div>{Array.from({ length: 5 }, (_, i) => <div key={i} className="skeleton skeleton--line" style={{ height: 16, margin: '18px 0' }} />)}</div>
      ) : (
        <ol className="nw-trending__list">
          {(articles || []).map((a, i) => (
            <li key={a.id}>
              <span className="nw-trending__rank" aria-hidden="true">{i + 1}</span>
              <div>
                <Link to={`/news/${a.id}`} className="nw-link nw-trending__title">{a.title}</Link>
                <SourceBadge name={a.source?.name} time={a.last_activity_at || a.published_at} count={sourceCount(a)} />
              </div>
            </li>
          ))}
          {!articles?.length && <li className="muted text-sm">Nothing is trending yet.</li>}
        </ol>
      )}
    </Card>
  );
}

// ------------------------------------------------------------ what's happening now
export function WhatsHappening({ groups, loading, categories }) {
  if (loading && !groups?.length) {
    return (
      <section>
        <div className="nw-section-head"><h2><Radio size={18} aria-hidden="true" /> What's happening now</h2></div>
        <div className="nw-now">{Array.from({ length: 3 }, (_, i) => <div key={i} className="skeleton" style={{ height: 210, borderRadius: 14 }} />)}</div>
      </section>
    );
  }
  if (!groups?.length) return null;
  return (
    <section aria-labelledby="now-h">
      <div className="nw-section-head">
        <h2 id="now-h"><Radio size={18} aria-hidden="true" /> What's happening now</h2>
        <span className="text-sm muted">Related coverage grouped into stories</span>
      </div>
      <div className="nw-now">
        {groups.map((g) => (
          <Card key={g.key} className="nw-now__group" as="section" aria-label={g.label}>
            <h3 className="nw-now__label"><span aria-hidden="true">{g.icon}</span> {g.label}</h3>
            <ul className="nw-now__list">
              {g.articles.map((a) => {
                const n = sourceCount(a);
                return (
                  <li key={a.id}>
                    <Link to={`/news/${a.id}`} className="nw-link nw-now__title">{a.title}</Link>
                    <div className="nw-now__meta">
                      <strong>{n} source{n === 1 ? '' : 's'}</strong>
                      <span aria-hidden="true">·</span>
                      <span>Updated {timeAgo(a.last_activity_at || a.published_at)}</span>
                      <ChevronRight size={14} aria-hidden="true" />
                    </div>
                  </li>
                );
              })}
            </ul>
          </Card>
        ))}
      </div>
    </section>
  );
}

// -------------------------------------------------------------------- states
export function LoadMore({ hasMore, loading, onClick, shown, total }) {
  if (!hasMore && !shown) return null;
  return (
    <div className="nw-loadmore">
      {hasMore ? (
        <Button variant="secondary" size="lg" loading={loading} onClick={onClick}>
          Load more
        </Button>
      ) : (
        <p className="muted text-sm">You're all caught up — {total} {total === 1 ? 'story' : 'stories'} shown.</p>
      )}
      {hasMore && <p className="muted text-xs">Showing {shown} of {total}</p>}
    </div>
  );
}

export function FeedError({ message, onRetry }) {
  return (
    <Banner tone="error" title="Unable to load news" action={<Button size="sm" variant="secondary" onClick={onRetry}>Try again</Button>}>
      {message}
    </Banner>
  );
}

export function NoNews({ searching, onClear, icon }) {
  return (
    <EmptyState icon={icon} title={searching ? 'No stories match your search' : 'No stories here yet'} action={onClear && <Button variant="secondary" onClick={onClear}>Clear search &amp; filters</Button>}>
      {searching
        ? 'Try different keywords, or remove a filter such as the source or date range.'
        : 'News is collected automatically every few minutes. If this is a fresh install, give it a minute, or fetch sources from News Admin.'}
    </EmptyState>
  );
}
