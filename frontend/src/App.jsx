import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { ToastProvider } from './context/ToastContext';
import { CasefileProvider } from './context/CasefileContext';
import AppLayout from './components/layout/AppLayout';
import BrochurePage from './pages/BrochurePage';
import TargetPage from './pages/TargetPage';
import PitchPage from './pages/PitchPage';
import OutreachPage from './pages/OutreachPage';
import ExportPage from './pages/ExportPage';
import AeoGeoPage from './pages/AeoGeoPage';
import NotFoundPage from './pages/NotFoundPage';
import EventsPage from './pages/events/EventsPage';
import EventDetailPage from './pages/events/EventDetailPage';
import AdminLayout from './pages/admin/AdminLayout';
import AdminEventsPage from './pages/admin/AdminEventsPage';
import AdminEventFormPage from './pages/admin/AdminEventFormPage';
import AdminDuplicatesPage from './pages/admin/AdminDuplicatesPage';
import AdminSourcesPage from './pages/admin/AdminSourcesPage';
import AdminErrorsPage from './pages/admin/AdminErrorsPage';

import NewsDashboard from './pages/news/NewsDashboard';
import NewsDetail from './pages/news/NewsDetail';
import StoryRedirect from './pages/news/StoryRedirect';
import NewsAdminLayout from './pages/news/admin/NewsAdminLayout';
import NewsSourcesPage from './pages/news/admin/NewsSourcesPage';
import NewsCategoriesPage from './pages/news/admin/NewsCategoriesPage';
import NewsErrorsPage from './pages/news/admin/NewsErrorsPage';

// Vite's BASE_URL is "/casefile/" — the path FastAPI serves the build from.
const basename = import.meta.env.BASE_URL.replace(/\/$/, '');

export default function App() {
  return (
    <BrowserRouter basename={basename}>
      <ToastProvider>
        <CasefileProvider>
          <Routes>
            <Route element={<AppLayout />}>
              <Route index element={<Navigate to="/brochure" replace />} />
              <Route path="brochure" element={<BrochurePage />} />
              <Route path="target" element={<TargetPage />} />
              <Route path="pitch" element={<PitchPage />} />
              <Route path="outreach" element={<OutreachPage />} />
              <Route path="export" element={<ExportPage />} />
              <Route path="aeo-geo" element={<AeoGeoPage />} />
              <Route path="events" element={<EventsPage />} />
              <Route path="events/:slug" element={<EventDetailPage />} />
              <Route path="admin" element={<AdminLayout />}>
                <Route index element={<Navigate to="events" replace />} />
                <Route path="events" element={<AdminEventsPage />} />
                <Route path="events/new" element={<AdminEventFormPage />} />
                <Route path="events/:id/edit" element={<AdminEventFormPage />} />
                <Route path="duplicates" element={<AdminDuplicatesPage />} />
                <Route path="sources" element={<AdminSourcesPage />} />
                <Route path="errors" element={<AdminErrorsPage />} />
              </Route>
              <Route path="news" element={<NewsDashboard />} />
              <Route path="news/story/:storyId" element={<StoryRedirect />} />
              <Route path="news/:id" element={<NewsDetail />} />
              <Route path="news-admin" element={<NewsAdminLayout />}>
                <Route index element={<NewsSourcesPage />} />
                <Route path="categories" element={<NewsCategoriesPage />} />
                <Route path="errors" element={<NewsErrorsPage />} />
              </Route>
              <Route path="*" element={<NotFoundPage />} />
            </Route>
          </Routes>
        </CasefileProvider>
      </ToastProvider>
    </BrowserRouter>
  );
}
