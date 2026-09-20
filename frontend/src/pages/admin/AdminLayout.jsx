import { NavLink, Outlet } from 'react-router-dom';
import { LogOut, Plus } from 'lucide-react';
import { Button, LinkButton, PageHeader } from '../../components/ui';
import AdminLogin from '../../components/admin/AdminLogin';
import { useAdminAuth } from '../../hooks/useAdminAuth';
import { useDocumentTitle } from '../../hooks/useDocumentTitle';

const TABS = [
  { to: '/admin/events', label: 'Events' },
  { to: '/admin/duplicates', label: 'Duplicates' },
  { to: '/admin/sources', label: 'Source health' },
  { to: '/admin/errors', label: 'Ingestion errors' },
];

export default function AdminLayout() {
  useDocumentTitle('Event Admin');
  const auth = useAdminAuth();

  if (!auth.authed) {
    return (
      <>
        <PageHeader eyebrow="Event Hub" title="Event admin" description="Add, edit, approve and merge events, and monitor where event data comes from." />
        <AdminLogin auth={auth} what="Event Hub admin" />
      </>
    );
  }

  return (
    <>
      <PageHeader
        eyebrow="Event Hub"
        title="Event admin"
        description="Add, edit, approve and merge events, and monitor where event data comes from."
        actions={
          <>
            <LinkButton to="/admin/events/new" icon={Plus}>Add event</LinkButton>
            <Button variant="secondary" icon={LogOut} onClick={auth.logout}>Sign out</Button>
          </>
        }
      />
      <nav className="adm-tabs" aria-label="Admin sections">
        {TABS.map((t) => (
          <NavLink key={t.to} to={t.to} className={({ isActive }) => `adm-tab ${isActive ? 'is-active' : ''}`}>
            {t.label}
          </NavLink>
        ))}
      </nav>
      <Outlet />
    </>
  );
}
