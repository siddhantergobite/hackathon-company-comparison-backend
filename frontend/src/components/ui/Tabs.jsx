// Accessible tab strip (arrow keys, roving tabindex). Pair each tab with a
// <TabPanel> that uses the same idPrefix + tab id.
export function Tabs({ tabs, value, onChange, idPrefix, label }) {
  const onKeyDown = (e) => {
    const i = tabs.findIndex((t) => t.id === value);
    let next = null;
    if (e.key === 'ArrowRight') next = tabs[(i + 1) % tabs.length];
    if (e.key === 'ArrowLeft') next = tabs[(i - 1 + tabs.length) % tabs.length];
    if (e.key === 'Home') next = tabs[0];
    if (e.key === 'End') next = tabs[tabs.length - 1];
    if (next) {
      e.preventDefault();
      onChange(next.id);
      document.getElementById(`${idPrefix}-tab-${next.id}`)?.focus();
    }
  };

  return (
    <div className="tabs" role="tablist" aria-label={label} onKeyDown={onKeyDown}>
      {tabs.map((t) => (
        <button
          key={t.id}
          id={`${idPrefix}-tab-${t.id}`}
          type="button"
          role="tab"
          className="tabs__tab"
          aria-selected={value === t.id}
          aria-controls={`${idPrefix}-panel-${t.id}`}
          tabIndex={value === t.id ? 0 : -1}
          onClick={() => onChange(t.id)}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

export function TabPanel({ idPrefix, id, children }) {
  return (
    <div
      id={`${idPrefix}-panel-${id}`}
      role="tabpanel"
      aria-labelledby={`${idPrefix}-tab-${id}`}
      className="card tabpanel"
      tabIndex={0}
    >
      {children}
    </div>
  );
}
