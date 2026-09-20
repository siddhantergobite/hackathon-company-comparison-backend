import { useEffect, useMemo, useState } from 'react';
import { Save } from 'lucide-react';
import { eventsApi } from '../../api/events';
import { Banner, Button, Card, CardHeader, LinkButton } from '../ui';
import TagInput from '../ui/TagInput';
import { Field } from './AdminBits';
import { BLANK_FORM, EVENT_TYPES, toPayload, validate } from './eventFormModel';

const timezones = (() => {
  try {
    return Intl.supportedValuesOf('timeZone');
  } catch {
    return [];
  }
})();

export default function EventForm({ initial = BLANK_FORM, editing = false, saving = false, serverError = '', onSubmit }) {
  const [f, setF] = useState(initial);
  const [errors, setErrors] = useState({});
  const [categoryOptions, setCategoryOptions] = useState([]);

  useEffect(() => {
    eventsApi.categories({ include_empty: true }).then((c) => setCategoryOptions(c.map((x) => x.name))).catch(() => {});
  }, []);

  const set = (k) => (e) => setF((s) => ({ ...s, [k]: e.target.value }));
  const setVal = (k) => (v) => setF((s) => ({ ...s, [k]: v }));
  const online = f.format === 'online';
  const input = (k, props = {}) => <input id={`f-${k}`} className="input" value={f[k]} onChange={set(k)} aria-invalid={Boolean(errors[k])} {...props} />;
  const err = (k) => errors[k] && <p className="adm-error" role="alert">{errors[k]}</p>;
  const suggestions = useMemo(() => categoryOptions, [categoryOptions]);

  const submit = (e) => {
    e.preventDefault();
    const found = validate(f);
    setErrors(found);
    if (Object.keys(found).length) {
      document.getElementById(`f-${Object.keys(found)[0]}`)?.focus();
      return;
    }
    onSubmit(toPayload(f, { editing }));
  };

  return (
    <form onSubmit={submit} className="stack stack--lg" noValidate>
      {serverError && <Banner tone="error" title="Couldn't save the event">{serverError}</Banner>}

      <Card>
        <CardHeader title="Basics" />
        <div className="adm-grid">
          <Field label="Title" htmlFor="f-title" required wide>{input('title', { maxLength: 300 })}{err('title')}</Field>
          <Field label="Event type" htmlFor="f-event_type" hint="Leave blank to classify automatically.">
            <select id="f-event_type" className="input" value={f.event_type} onChange={set('event_type')}>
              <option value="">Auto-detect</option>
              {EVENT_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </Field>
          <Field label="Format" htmlFor="f-format">
            <select id="f-format" className="input" value={f.format} onChange={set('format')}>
              <option value="offline">In person</option><option value="online">Online</option><option value="hybrid">Hybrid</option>
            </select>
          </Field>
          <Field label="Summary" htmlFor="f-summary" hint="One or two sentences shown on the event card. Auto-generated if blank." wide>
            <textarea id="f-summary" className="input" rows={2} maxLength={1000} value={f.summary} onChange={set('summary')} />
          </Field>
          <Field label="Description" htmlFor="f-description" wide>
            <textarea id="f-description" className="input" rows={7} value={f.description} onChange={set('description')} />
          </Field>
          {editing && (
            <Field label="URL slug" htmlFor="f-slug" hint="Changing it keeps the old link working.">{input('slug')}</Field>
          )}
        </div>
      </Card>

      <Card>
        <CardHeader title="Date & time" />
        <div className="adm-grid adm-grid--4">
          <Field label="Start date" htmlFor="f-start_date" required>{input('start_date', { type: 'date' })}{err('start_date')}</Field>
          <Field label="End date" htmlFor="f-end_date">{input('end_date', { type: 'date', min: f.start_date || undefined })}{err('end_date')}</Field>
          <Field label="Start time" htmlFor="f-start_time">{input('start_time', { type: 'time' })}</Field>
          <Field label="End time" htmlFor="f-end_time">{input('end_time', { type: 'time' })}</Field>
          <Field label="Timezone" htmlFor="f-timezone" hint="e.g. America/Los_Angeles">
            {input('timezone', { list: 'tz-list', placeholder: 'Europe/Berlin' })}
            <datalist id="tz-list">{timezones.map((t) => <option key={t} value={t} />)}</datalist>
          </Field>
        </div>
      </Card>

      <Card>
        <CardHeader title="Location" />
        {online ? (
          <p className="muted">Online events don't need a physical location.</p>
        ) : (
          <div className="adm-grid">
            <Field label="Venue" htmlFor="f-venue">{input('venue')}</Field>
            <Field label="Address" htmlFor="f-address">{input('address')}</Field>
            <Field label="City" htmlFor="f-city">{input('city')}</Field>
            <Field label="State / region" htmlFor="f-state">{input('state')}</Field>
            <Field label="Country" htmlFor="f-country" hint="Country names or codes (US, IN, Germany) are normalised.">{input('country')}</Field>
            <div className="adm-grid adm-grid--2">
              <Field label="Latitude" htmlFor="f-latitude">{input('latitude', { inputMode: 'decimal' })}{err('latitude')}</Field>
              <Field label="Longitude" htmlFor="f-longitude">{input('longitude', { inputMode: 'decimal' })}{err('longitude')}</Field>
            </div>
          </div>
        )}
      </Card>

      <Card>
        <CardHeader title="Classification" />
        <div className="adm-grid">
          <Field label="Categories / industries" htmlFor="f-categories" hint="Press Enter to add. Aliases like “ai” are mapped automatically." wide>
            <TagInput id="f-categories" value={f.categories} onChange={setVal('categories')} suggestions={suggestions} placeholder="Artificial Intelligence, FinTech…" label="Categories" />
          </Field>
          <Field label="Topics" htmlFor="f-topics">
            <TagInput id="f-topics" value={f.topics} onChange={setVal('topics')} placeholder="Generative AI, LLM…" label="Topics" />
          </Field>
          <Field label="Target audience" htmlFor="f-audience">
            <TagInput id="f-audience" value={f.audience} onChange={setVal('audience')} placeholder="Founders, CTOs…" label="Target audience" />
          </Field>
        </div>
      </Card>

      <Card>
        <CardHeader title="Organizer" />
        <div className="adm-grid">
          <Field label="Name" htmlFor="f-organizer_name">{input('organizer_name')}</Field>
          <Field label="Website" htmlFor="f-organizer_website">{input('organizer_website', { type: 'url', placeholder: 'https://' })}</Field>
          <Field label="Description" htmlFor="f-organizer_description" wide>
            <textarea id="f-organizer_description" className="input" rows={2} value={f.organizer_description} onChange={set('organizer_description')} />
          </Field>
        </div>
      </Card>

      <Card>
        <CardHeader title="Registration & links" />
        <div className="adm-grid adm-grid--4">
          <Field label="Price" htmlFor="f-price" hint="0 = free">{input('price', { inputMode: 'decimal' })}{err('price')}</Field>
          <Field label="Currency" htmlFor="f-currency">{input('currency', { maxLength: 3, placeholder: 'USD' })}</Field>
          <Field label="Ticket type" htmlFor="f-ticket_type">
            <select id="f-ticket_type" className="input" value={f.ticket_type} onChange={set('ticket_type')}>
              <option value="">Auto (from price)</option><option value="free">Free</option><option value="paid">Paid</option>
            </select>
          </Field>
        </div>
        <div className="adm-grid" style={{ marginTop: 16 }}>
          <Field label="Ticket information" htmlFor="f-ticket_info" wide>{input('ticket_info')}</Field>
          <Field label="Registration URL" htmlFor="f-reg_url">{input('reg_url', { type: 'url', placeholder: 'https://' })}</Field>
          <Field label="Official event website" htmlFor="f-event_url">{input('event_url', { type: 'url', placeholder: 'https://' })}</Field>
          <Field label="Image URL" htmlFor="f-image_url" wide>{input('image_url', { type: 'url', placeholder: 'https://' })}</Field>
        </div>
      </Card>

      <Card>
        <CardHeader title="Status" />
        <Field label="Event status" htmlFor="f-status" hint="Upcoming / ongoing / completed are set automatically from the dates.">
          <select id="f-status" className="input" value={f.status} onChange={set('status')}>
            <option value="">Automatic</option><option value="cancelled">Cancelled</option><option value="postponed">Postponed</option>
          </select>
        </Field>
      </Card>

      <div className="adm-formbar">
        <LinkButton to="/admin/events" variant="secondary">Cancel</LinkButton>
        <Button type="submit" icon={Save} loading={saving}>{editing ? 'Save changes' : 'Create event'}</Button>
      </div>
    </form>
  );
}
