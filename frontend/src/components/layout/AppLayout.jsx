import { useEffect, useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import Sidebar from './Sidebar';
import Topbar from './Topbar';
import { useTheme } from '../../hooks/useTheme';

export default function AppLayout() {
  const [menuOpen, setMenuOpen] = useState(false);
  const { theme, toggle } = useTheme();
  const { pathname } = useLocation();

  useEffect(() => {
    setMenuOpen(false);
    window.scrollTo(0, 0);
  }, [pathname]);

  useEffect(() => {
    if (!menuOpen) return undefined;
    const onKey = (e) => e.key === 'Escape' && setMenuOpen(false);
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [menuOpen]);

  return (
    <div className="app-shell">
      <Sidebar open={menuOpen} onNavigate={() => setMenuOpen(false)} />
      <div
        className={`sidebar-backdrop ${menuOpen ? 'is-open' : ''}`}
        onClick={() => setMenuOpen(false)}
        aria-hidden="true"
      />
      <div className="main-col">
        <Topbar theme={theme} onToggleTheme={toggle} onOpenMenu={() => setMenuOpen(true)} />
        <main className={`page ${/^\/(events|admin|news)/.test(pathname) ? 'page--wide' : ''}`} id="main">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
