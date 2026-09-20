import { NavLink, Outlet } from 'react-router-dom';
import { LogOut } from 'lucide-react';
import { Button, PageHeader } from '../../../components/ui';
import AdminLogin from '../../../components/admin/AdminLogin';
import { newsAdminApi } from '../../../api/news';
import { useAdminAuth } from '../../../hooks/useAdminAuth';
import { useDocumentTitle } from '../../../hooks/useDocumentTitle';

const TABS = [
  { to: '/news-admin', label: 'Sources', end: true },
  { to: '/news-admin/categories', label: 'Categories' },
  { to: '/news-admin/errors', label: 'Errors & runs' },
];

const TITLE = 'News admin';
const DESC = 'Add and configure news sources, watch their health, manage categories and review ingestion errors.';

export default function NewsAdminLayout() {
  useDocumentTitle(TITLE);
  const auth = useAdminAuth(newsAdminApi.verify);

  if (!auth.authed) {
    return (
      <>
        <PageHeader eyebrow="News Intelligence" title={TITLE} description={DESC} />
        <AdminLogin auth={auth} what="News admin" envName="NEWS_ADMIN_API_KEY (or EVENT_ADMIN_API_KEY)" />
      </>
    );
  }
  return (
    <>
      <PageHeader eyebrow="News Intelligence" title={TITLE} description={DESC} actions={<Button variant="secondary" icon={LogOut} onClick={auth.logout}>Sign out</Button>} />
      <nav className="adm-tabs" aria-label="News admin sections">
        {TABS.map((t) => (
          <NavLink key={t.to} to={t.to} end={t.end} className={({ isActive }) => `adm-tab ${isActive ? 'is-active' : ''}`}>
            {t.label}
          </NavLink>
        ))}
      </nav>
      <Outlet />
    </>
  );
}
