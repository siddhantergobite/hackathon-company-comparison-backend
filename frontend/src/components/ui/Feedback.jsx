import { useEffect, useState } from 'react';
import { AlertCircle, AlertTriangle, CheckCircle2, Info, Loader2 } from 'lucide-react';
import { Card } from './Card';
import { LinkButton } from './Button';

const BANNER_ICONS = { info: Info, success: CheckCircle2, warning: AlertTriangle, error: AlertCircle };

export function Banner({ tone = 'info', title, children, action }) {
  const Icon = BANNER_ICONS[tone] || Info;
  return (
    <div className={`banner banner--${tone}`} role={tone === 'error' ? 'alert' : 'status'}>
      <Icon size={18} className="banner__icon" aria-hidden="true" />
      <div style={{ flex: 1, minWidth: 0 }}>
        {title && <div className="banner__title">{title}</div>}
        {children && <div className="banner__body">{children}</div>}
      </div>
      {action}
    </div>
  );
}

// Progress is indicative only (the API gives no progress events): it eases toward
// ~94% and never reaches 100% until the request actually finishes.
export function LoadingPanel({ title, steps = [] }) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const id = window.setInterval(() => setElapsed((s) => s + 1), 1000);
    return () => window.clearInterval(id);
  }, []);

  const stepIndex = steps.length ? Math.min(steps.length - 1, Math.floor(elapsed / 7)) : 0;
  const pct = Math.min(94, Math.round(100 * (1 - Math.exp(-elapsed / 45))));

  return (
    <Card role="status" aria-live="polite">
      <div className="loading-panel">
        <Loader2 size={34} className="loading-panel__spinner spin" aria-hidden="true" />
        <div className="loading-panel__title">{title}</div>
        <div className="loading-panel__step">{steps[stepIndex] || 'Working…'}</div>
        <div className="loading-panel__bar" aria-hidden="true">
          <span style={{ width: `${pct}%` }} />
        </div>
        <div className="text-xs muted">{elapsed}s elapsed</div>
      </div>
    </Card>
  );
}

export function EmptyState({ icon: Icon, title, children, action }) {
  return (
    <Card>
      <div className="empty-state">
        {Icon && (
          <div className="empty-state__icon">
            <Icon size={26} aria-hidden="true" />
          </div>
        )}
        <h3>{title}</h3>
        {children && <p>{children}</p>}
        {action}
      </div>
    </Card>
  );
}

// Shown when a page needs earlier exhibits that haven't been completed yet.
export function Prerequisite({ items }) {
  const missing = items.filter((i) => !i.done);
  if (!missing.length) return null;
  return (
    <Banner
      tone="warning"
      title="Complete the earlier steps first"
      action={
        <div className="row" style={{ flexShrink: 0 }}>
          {missing.map((m) => (
            <LinkButton key={m.to} to={m.to} size="sm" variant="secondary">
              {m.label}
            </LinkButton>
          ))}
        </div>
      }
    >
      {missing.map((m) => m.reason).join(' ')}
    </Banner>
  );
}
