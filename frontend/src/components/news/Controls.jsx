import { useEffect, useRef, useState } from 'react';
import { Search, X } from 'lucide-react';
import { DATE_PRESETS, SORTS } from '../../utils/news';
import { useDebounced } from '../../hooks/useNews';

// --------------------------------------------------------------------- search bar
// Typing is debounced into the URL; changes made elsewhere (clear, Back) flow back in.
export function NewsSearchBar({ value, onSearch, placeholder = 'Search news…  OpenAI, India economy, AI agents, Tesla', size = 'md' }) {
  const [text, setText] = useState(value);
  const debounced = useDebounced(text, 400);
  const last = useRef(value);

  useEffect(() => {
    if (debounced !== last.current) {
      last.current = debounced;
      onSearch(debounced);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced]);
  useEffect(() => {
    if (value !== last.current) {
      last.current = value;
      setText(value);
    }
  }, [value]);

  return (
    <form className={`nw-search nw-search--${size}`} role="search" onSubmit={(e) => { e.preventDefault(); last.current = text; onSearch(text); }}>
      <Search size={18} aria-hidden="true" />
      <input type="search" value={text} onChange={(e) => setText(e.target.value)} placeholder={placeholder} aria-label="Search news" />
      {text && (
        <button type="button" className="nw-search__clear" onClick={() => setText('')} aria-label="Clear search">
          <X size={16} />
        </button>
      )}
    </form>
  );
}

// ---------------------------------------------------------------- category tabs
export function CategoryTabs({ categories, value, onChange }) {
  if (!categories.length) return <div className="nw-tabs nw-tabs--empty skeleton" aria-hidden="true" />;
  return (
    <nav className="nw-tabs" aria-label="News categories">
      <div className="nw-tabs__row" role="tablist">
        {categories.map((c) => (
          <button
            key={c.slug}
            type="button"
            role="tab"
            aria-selected={value === c.slug}
            className={`nw-tab ${value === c.slug ? 'is-active' : ''} ${c.slug === 'breaking' ? 'nw-tab--breaking' : ''}`}
            onClick={() => onChange(c.slug)}
          >
            {c.icon && <span aria-hidden="true">{c.icon}</span>}
            {c.name}
            {c.count > 0 && c.slug !== 'all' && <span className="nw-tab__count">{c.count}</span>}
          </button>
        ))}
      </div>
    </nav>
  );
}

// ------------------------------------------------------------------- feed filters
export function NewsFilters({ filters, update, sources, topics, activeCount, onClear }) {
  return (
    <div className="nw-filters" role="group" aria-label="Filter news">
      <label className="nw-filter">
        <span>Source</span>
        <select className="input" value={filters.source} onChange={(e) => update({ source: e.target.value })}>
          <option value="">All sources</option>
          {sources.map((s) => <option key={s.name} value={s.name}>{s.name} ({s.count})</option>)}
        </select>
      </label>
      <label className="nw-filter">
        <span>Date</span>
        <select className="input" value={filters.date} onChange={(e) => update({ date: e.target.value })}>
          {DATE_PRESETS.map((d) => <option key={d.value || 'any'} value={d.value}>{d.label}</option>)}
        </select>
      </label>
      {filters.date === 'custom' && (
        <>
          <label className="nw-filter">
            <span>From</span>
            <input type="date" className="input" value={filters.from} max={filters.to || undefined} onChange={(e) => update({ date: 'custom', from: e.target.value })} />
          </label>
          <label className="nw-filter">
            <span>To</span>
            <input type="date" className="input" value={filters.to} min={filters.from || undefined} onChange={(e) => update({ date: 'custom', to: e.target.value })} />
          </label>
        </>
      )}
      <label className="nw-filter">
        <span>Topic</span>
        <select className="input" value={filters.topic} onChange={(e) => update({ topic: e.target.value })}>
          <option value="">All topics</option>
          {filters.topic && !topics.some((t) => t.name === filters.topic) && <option value={filters.topic}>{filters.topic}</option>}
          {topics.map((t) => <option key={t.name} value={t.name}>{t.name} ({t.count})</option>)}
        </select>
      </label>
      <label className="nw-filter">
        <span>Sort</span>
        <select className="input" value={filters.sort} onChange={(e) => update({ sort: e.target.value })}>
          {SORTS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
        </select>
      </label>
      {activeCount > 0 && (
        <button type="button" className="nw-filters__clear" onClick={onClear}>
          <X size={14} aria-hidden="true" /> Clear filters
        </button>
      )}
    </div>
  );
}
