import { useState } from 'react';
import { RotateCcw } from 'lucide-react';
import Button from '../ui/Button';
import { DATE_PRESETS } from '../../utils/events';

function Group({ title, children }) {
  return (
    <fieldset className="ev-filter-group">
      <legend>{title}</legend>
      {children}
    </fieldset>
  );
}

function Segmented({ name, value, options, onChange }) {
  return (
    <div className="ev-segmented" role="radiogroup" aria-label={name}>
      {options.map((o) => (
        <button key={o.value} type="button" role="radio" aria-checked={value === o.value} className={value === o.value ? 'is-on' : ''} onClick={() => onChange(o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

const toggle = (list, v) => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);

export default function FilterPanel({ filters, update, facets, activeCount, onClear }) {
  const [showAllCats, setShowAllCats] = useState(false);
  const types = facets.types.filter((t) => t.count > 0 || filters.type.includes(t.value));
  const cats = facets.categories;
  const shownCats = showAllCats ? cats : cats.slice(0, 8);
  const { countries, states, cities } = facets.locations;

  return (
    <div className="ev-filters">
      <div className="ev-filters__head">
        <h2>Filters</h2>
        <Button variant="ghost" size="sm" icon={RotateCcw} onClick={onClear} disabled={!activeCount}>
          Reset
        </Button>
      </div>

      <Group title="Event type">
        {types.length ? (
          <ul className="ev-checklist">
            {types.map((t) => (
              <li key={t.value}>
                <label>
                  <input type="checkbox" checked={filters.type.includes(t.value)} onChange={() => update({ type: toggle(filters.type, t.value) })} />
                  <span>{t.label}</span>
                  <span className="ev-checklist__count">{t.count}</span>
                </label>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm muted">No types available yet.</p>
        )}
      </Group>

      <Group title="Industry">
        {cats.length ? (
          <>
            <ul className="ev-checklist">
              {shownCats.map((c) => (
                <li key={c.name}>
                  <label>
                    <input type="checkbox" checked={filters.category.includes(c.name)} onChange={() => update({ category: toggle(filters.category, c.name) })} />
                    <span>{c.name}</span>
                    <span className="ev-checklist__count">{c.count}</span>
                  </label>
                </li>
              ))}
            </ul>
            {cats.length > 8 && (
              <button type="button" className="ev-linkbtn" onClick={() => setShowAllCats((s) => !s)}>
                {showAllCats ? 'Show fewer' : `Show all ${cats.length}`}
              </button>
            )}
          </>
        ) : (
          <p className="text-sm muted">No industries available yet.</p>
        )}
      </Group>

      <Group title="Location">
        <label className="ev-field">
          <span>Country</span>
          <select className="input" value={filters.country} onChange={(e) => update({ country: e.target.value })}>
            <option value="">All countries</option>
            {countries.map((c) => (
              <option key={c.name} value={c.name}>
                {c.name} ({c.count})
              </option>
            ))}
          </select>
        </label>
        <label className="ev-field">
          <span>State / region</span>
          <select className="input" value={filters.state} disabled={!filters.country || !states.length} onChange={(e) => update({ state: e.target.value })}>
            <option value="">All states</option>
            {states.map((s) => (
              <option key={s.name} value={s.name}>
                {s.name} ({s.count})
              </option>
            ))}
          </select>
        </label>
        <label className="ev-field">
          <span>City</span>
          <select className="input" value={filters.city} disabled={!filters.country || !cities.length} onChange={(e) => update({ city: e.target.value })}>
            <option value="">All cities</option>
            {cities.map((c) => (
              <option key={c.name} value={c.name}>
                {c.name} ({c.count})
              </option>
            ))}
          </select>
        </label>
      </Group>

      <Group title="Date">
        <ul className="ev-checklist ev-checklist--radio">
          {DATE_PRESETS.map((d) => (
            <li key={d.value || 'any'}>
              <label>
                <input type="radio" name="date-preset" checked={filters.date === d.value} onChange={() => update({ date: d.value })} />
                <span>{d.label}</span>
              </label>
            </li>
          ))}
        </ul>
        {filters.date === 'custom' && (
          <div className="ev-daterange">
            <label className="ev-field">
              <span>From</span>
              <input type="date" className="input" value={filters.from} max={filters.to || undefined} onChange={(e) => update({ date: 'custom', from: e.target.value })} />
            </label>
            <label className="ev-field">
              <span>To</span>
              <input type="date" className="input" value={filters.to} min={filters.from || undefined} onChange={(e) => update({ date: 'custom', to: e.target.value })} />
            </label>
          </div>
        )}
      </Group>

      <Group title="Format">
        <Segmented
          name="Format"
          value={filters.format}
          onChange={(format) => update({ format })}
          options={[{ value: '', label: 'Any' }, { value: 'offline', label: 'In person' }, { value: 'online', label: 'Online' }, { value: 'hybrid', label: 'Hybrid' }]}
        />
      </Group>

      <Group title="Price">
        <Segmented name="Price" value={filters.price} onChange={(price) => update({ price })} options={[{ value: '', label: 'Any' }, { value: 'free', label: 'Free' }, { value: 'paid', label: 'Paid' }]} />
      </Group>
    </div>
  );
}
