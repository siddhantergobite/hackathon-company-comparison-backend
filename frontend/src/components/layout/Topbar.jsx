import { useLocation } from 'react-router-dom';
import { Menu, Moon, Sun } from 'lucide-react';
import { useCasefile } from '../../context/CasefileContext';
import { findPage } from '../../config/navigation';
import { getTargetName } from '../../utils/target';

export default function Topbar({ theme, onToggleTheme, onOpenMenu }) {
  const { brochure, target } = useCasefile();
  const { pathname } = useLocation();
  const page = findPage(pathname);

  return (
    <div className="topbar">
      <button type="button" className="icon-btn topbar__menu" onClick={onOpenMenu} aria-label="Open navigation">
        <Menu size={20} />
      </button>

      <div className="topbar__crumbs">
        <span>Casefile</span>
        <span aria-hidden="true">/</span>
        <strong className="truncate">{page ? (page.exhibit ? `Exhibit ${page.exhibit} — ${page.title}` : page.title) : 'Not found'}</strong>
      </div>

      {page?.exhibit && (
      <div className="topbar__ctx">
        <span className="ctx-pill" title="Your company (Exhibit A)">
          <span className="ctx-pill__label">You</span>
          <span className="ctx-pill__value">{brochure?.company_name || 'Not set'}</span>
        </span>
        <span className="ctx-pill" title="Target company (Exhibit B)">
          <span className="ctx-pill__label">Target</span>
          <span className="ctx-pill__value">{target ? getTargetName(target) : 'Not set'}</span>
        </span>
      </div>
      )}
      {!page?.exhibit && <div style={{ flex: 0 }} />}

      <button
        type="button"
        className="icon-btn"
        onClick={onToggleTheme}
        aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
        title={theme === 'dark' ? 'Light theme' : 'Dark theme'}
      >
        {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
      </button>
    </div>
  );
}
