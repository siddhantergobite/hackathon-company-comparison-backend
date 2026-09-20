import { X } from 'lucide-react';
import { DATE_PRESETS } from '../../utils/events';

// Removable chips summarising the applied filters.
export default function ActiveFilters({ filters, update, typeLabels, onClear }) {
  const chips = [];
  filters.type.forEach((t) => chips.push({ key: `t-${t}`, label: typeLabels[t] || t, remove: () => update({ type: filters.type.filter((x) => x !== t) }) }));
  filters.category.forEach((c) => chips.push({ key: `c-${c}`, label: c, remove: () => update({ category: filters.category.filter((x) => x !== c) }) }));
  if (filters.country) chips.push({ key: 'country', label: filters.country, remove: () => update({ country: '' }) });
  if (filters.state) chips.push({ key: 'state', label: filters.state, remove: () => update({ state: '' }) });
  if (filters.city) chips.push({ key: 'city', label: filters.city, remove: () => update({ city: '' }) });
  if (filters.date) {
    const label = filters.date === 'custom' ? `${filters.from || '…'} → ${filters.to || '…'}` : DATE_PRESETS.find((d) => d.value === filters.date)?.label;
    chips.push({ key: 'date', label, remove: () => update({ date: '' }) });
  }
  if (filters.format) chips.push({ key: 'format', label: { offline: 'In person', online: 'Online', hybrid: 'Hybrid' }[filters.format], remove: () => update({ format: '' }) });
  if (filters.price) chips.push({ key: 'price', label: filters.price === 'free' ? 'Free' : 'Paid', remove: () => update({ price: '' }) });

  if (!chips.length) return null;
  return (
    <div className="ev-active" aria-label="Active filters">
      {chips.map((c) => (
        <button key={c.key} type="button" className="ev-active__chip" onClick={c.remove} aria-label={`Remove filter ${c.label}`}>
          {c.label} <X size={13} aria-hidden="true" />
        </button>
      ))}
      <button type="button" className="ev-linkbtn" onClick={onClear}>
        Clear all
      </button>
    </div>
  );
}
