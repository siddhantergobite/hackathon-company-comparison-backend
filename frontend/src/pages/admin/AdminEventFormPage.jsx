import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { adminApi, apiErrorMessage } from '../../api/events';
import { Banner, LinkButton, LoadingPanel } from '../../components/ui';
import EventForm from '../../components/admin/EventForm';
import { toForm } from '../../components/admin/eventFormModel';
import { useToast } from '../../context/ToastContext';

export default function AdminEventFormPage() {
  const { id } = useParams();
  const editing = Boolean(id);
  const navigate = useNavigate();
  const toast = useToast();
  const [state, setState] = useState({ initial: null, loading: editing, error: '' });
  const [saving, setSaving] = useState(false);
  const [serverError, setServerError] = useState('');

  useEffect(() => {
    if (!editing) return;
    let live = true;
    adminApi
      .get(id)
      .then((e) => live && setState({ initial: toForm(e), loading: false, error: '' }))
      .catch((err) => live && setState({ initial: null, loading: false, error: apiErrorMessage(err) }));
    return () => {
      live = false;
    };
  }, [id, editing]);

  const submit = async (payload) => {
    setSaving(true);
    setServerError('');
    try {
      const saved = editing ? await adminApi.update(id, payload) : await adminApi.create(payload);
      toast.success(editing ? 'Event updated.' : 'Event created and published.');
      if (!editing && saved.possible_duplicate_of) toast.info('This looks similar to an existing event — check the Duplicates tab.');
      navigate('/admin/events');
    } catch (err) {
      setServerError(apiErrorMessage(err));
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } finally {
      setSaving(false);
    }
  };

  if (state.loading) return <LoadingPanel title="Loading event…" />;
  if (state.error) {
    return (
      <div className="stack">
        <Banner tone="error" title="Couldn't load the event">{state.error}</Banner>
        <div><LinkButton to="/admin/events" variant="secondary">Back to events</LinkButton></div>
      </div>
    );
  }
  return <EventForm key={id || 'new'} initial={state.initial || undefined} editing={editing} saving={saving} serverError={serverError} onSubmit={submit} />;
}
