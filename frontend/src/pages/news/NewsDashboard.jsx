import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Newspaper, RefreshCw } from 'lucide-react';
import { newsApi } from '../../api/news';
import { CategoryTabs, NewsFilters, NewsSearchBar } from '../../components/news/Controls';
import { FeedError, LoadMore, NewsGrid, NoNews, TopStories, TrendingStories, WhatsHappening } from '../../components/news/Lists';
import { TopicBadge } from '../../components/news/Badges';
import { Card } from '../../components/ui';
import { toFeedParams, useApi, useNewsFeed, useNewsFilters } from '../../hooks/useNews';
import { useDocumentTitle } from '../../hooks/useDocumentTitle';
import { timeAgo } from '../../utils/news';

const REFRESH = 90_000;

export default function NewsDashboard() {
  useDocumentTitle('News');
  const { filters, update, clear, activeCount } = useNewsFilters();
  const searching = Boolean(filters.q.trim());
  const browsing = !searching && filters.category === 'all' && activeCount === 0;

  const categories = useApi((s) => newsApi.categories(s), [], { refreshMs: 120_000 });
  const sources = useApi((s) => newsApi.sources(s), []);
  const topics = useApi((s) => newsApi.topics(20, s), []);
  const top = useApi((s) => newsApi.topStories(5, s), [], { refreshMs: REFRESH });
  const trending = useApi((s) => newsApi.trending(8, s), [], { refreshMs: REFRESH });
  const happening = useApi((s) => newsApi.happening(3, s), [], { refreshMs: REFRESH });
  const feed = useNewsFeed(toFeedParams(filters), { refreshMs: REFRESH });

  const cats = categories.data || [];
  const catMap = useMemo(() => Object.fromEntries(cats.map((c) => [c.slug, c])), [cats]);
  const current = catMap[filters.category];
  const total48 = catMap.all?.count;

  const [updatedAt, setUpdatedAt] = useState(Date.now());
  useEffect(() => { if (!feed.loading) setUpdatedAt(Date.now()); }, [feed.loading, feed.items]);
  const [, tick] = useState(0);
  useEffect(() => { const id = window.setInterval(() => tick((n) => n + 1), 30_000); return () => window.clearInterval(id); }, []);

  const heading = searching ? `Results for “${filters.q.trim()}”` : filters.category === 'all' ? 'Latest news' : `${current?.icon || ''} ${current?.name || filters.category}`.trim();

  return (
    <>
      <header className="nw-hero">
        <div className="nw-hero__eyebrow"><Newspaper size={15} aria-hidden="true" /> NEWS INTELLIGENCE</div>
        <h1>What's happening right now?</h1>
        <p>AI, technology, business, India and the world — collected from {sources.data?.length || 'dozens of'} publishers, with duplicate coverage grouped into single stories.</p>
        <NewsSearchBar value={filters.q} onSearch={(q) => update({ q }, { replace: true })} size="lg" />
        {total48 > 0 && <div className="nw-hero__stat">{total48.toLocaleString()} stories in the last 48 hours</div>}
      </header>

      <CategoryTabs categories={cats} value={filters.category} onChange={(category) => update({ category })} />

      <div className="nw-layout">
        <main className="nw-main">
          {browsing && (
            <>
              <TopStories articles={top.data} loading={top.loading} categories={catMap} />
              <WhatsHappening groups={happening.data} loading={happening.loading} categories={catMap} />
            </>
          )}

          <section aria-labelledby="feed-h">
            <div className="nw-section-head">
              <h2 id="feed-h">{heading}</h2>
              <div className="nw-live">
                <span className="nw-live__dot" aria-hidden="true" />
                <span>Updated {timeAgo(updatedAt) || 'just now'}</span>
                <button type="button" className="icon-btn icon-btn--sm" onClick={feed.reload} aria-label="Refresh news" title="Refresh">
                  <RefreshCw size={14} />
                </button>
              </div>
            </div>

            <NewsFilters filters={filters} update={update} sources={sources.data || []} topics={topics.data || []} activeCount={activeCount} onClear={() => clear(['category', 'q'])} />

            {searching && !feed.loading && <p className="nw-count" aria-live="polite">{feed.total.toLocaleString()} {feed.total === 1 ? 'story' : 'stories'} found</p>}

            {feed.error && !feed.items.length && <FeedError message={feed.error} onRetry={feed.reload} />}
            {!feed.error && !feed.loading && !feed.items.length && (
              <NoNews searching={searching || activeCount > 0} icon={Newspaper} onClear={searching || activeCount > 0 ? () => clear(['category']) : undefined} />
            )}

            {(feed.loading || feed.items.length > 0) && !(feed.error && !feed.items.length) && (
              <>
                <NewsGrid articles={feed.items} categories={catMap} loading={feed.loading} skeletons={6} />
                {feed.error && <p className="text-sm con" role="alert">{feed.error}</p>}
                <LoadMore hasMore={feed.hasMore} loading={feed.loadingMore} onClick={feed.loadMore} shown={feed.items.length} total={feed.total} />
              </>
            )}
          </section>
        </main>

        <aside className="nw-side" aria-label="Trending and topics">
          <TrendingStories articles={trending.data} loading={trending.loading} />
          {(topics.data || []).length > 0 && (
            <Card as="section" aria-labelledby="topics-h">
              <div className="nw-section-head nw-section-head--tight"><h2 id="topics-h">Popular topics</h2></div>
              <div className="nw-topics">
                {topics.data.slice(0, 14).map((t) => <TopicBadge key={t.name} topic={t.name} />)}
              </div>
            </Card>
          )}
          <p className="nw-attrib text-xs muted">
            Headlines, teasers and images belong to their publishers and link to the original articles. Summaries marked “AI” are generated from the headline and teaser only.
            {' '}<Link to="/news-admin">Manage sources</Link>
          </p>
        </aside>
      </div>
    </>
  );
}
