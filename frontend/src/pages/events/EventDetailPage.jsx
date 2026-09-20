import { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, CalendarClock, CalendarX2, FileText, Layers, MapPin, RefreshCw, Sparkles, Tags, Users, Video } from 'lucide-react';
import { apiErrorMessage, eventsApi, isCancel } from '../../api/events';
import { Banner, Button, EmptyState, LinkButton, Tag, TagList } from '../../components/ui';
import EventImage from '../../components/events/EventImage';
import { Fact, LocationSection, OrganizerCard, RegistrationCard, Section, SourceCard } from '../../components/events/detail/DetailParts';
import { useDocumentTitle } from '../../hooks/useDocumentTitle';
import { formatDateRange, formatFormat, formatLocation, formatLongDate, startCase, STATUS_LABEL } from '../../utils/events';

function DetailSkeleton() {
  return (
    <div aria-hidden="true">
      <div className="skeleton" style={{ height: 320, borderRadius: 18 }} />
      <div className="ev-detail__grid" style={{ marginTop: 24 }}>
        <div className="stack">
          <div className="skeleton" style={{ height: 180, borderRadius: 12 }} />
          <div className="skeleton" style={{ height: 140, borderRadius: 12 }} />
        </div>
        <div className="skeleton" style={{ height: 240, borderRadius: 12 }} />
      </div>
    </div>
  );
}

function timeLine(e) {
  if (!e.start_time && !e.end_time) return 'Time to be announced';
  const t = e.start_time && e.end_time ? `${e.start_time} – ${e.end_time}` : e.start_time || `until ${e.end_time}`;
  return e.timezone ? `${t} (${e.timezone})` : t;
}

export default function EventDetailPage() {
  const { slug } = useParams();
  const [state, setState] = useState({ event: null, loading: true, error: '', notFound: false });
  const [nonce, setNonce] = useState(0);
  const retry = useCallback(() => setNonce((n) => n + 1), []);

  useEffect(() => {
    const controller = new AbortController();
    setState({ event: null, loading: true, error: '', notFound: false });
    eventsApi
      .bySlug(slug, controller.signal)
      .then((event) => setState({ event, loading: false, error: '', notFound: false }))
      .catch((err) => {
        if (isCancel(err)) return;
        if (err.response?.status === 404) setState({ event: null, loading: false, error: '', notFound: true });
        else setState({ event: null, loading: false, error: apiErrorMessage(err, 'Unable to load this event'), notFound: false });
      });
    return () => controller.abort();
  }, [slug, nonce]);

  const { event, loading, error, notFound } = state;
  useDocumentTitle(event?.title || 'Event');

  const back = (
    <Link to="/events" className="ev-back">
      <ArrowLeft size={16} aria-hidden="true" /> All events
    </Link>
  );

  if (loading) return <><div className="ev-back-row">{back}</div><DetailSkeleton /></>;
  if (notFound) {
    return (
      <>
        <div className="ev-back-row">{back}</div>
        <EmptyState icon={CalendarX2} title="Event not found" action={<LinkButton to="/events">Browse events</LinkButton>}>
          This event doesn't exist, has ended and been removed, or is not published yet.
        </EmptyState>
      </>
    );
  }
  if (error) {
    return (
      <>
        <div className="ev-back-row">{back}</div>
        <Banner tone="error" title="Unable to load this event" action={<Button size="sm" variant="secondary" icon={RefreshCw} onClick={retry}>Try again</Button>}>
          {error}
        </Banner>
      </>
    );
  }

  const cats = event.categories || [];
  const topics = event.topics || [];
  const audience = event.audience || [];
  const sameDay = event.start_date === event.end_date;
  const status = STATUS_LABEL[event.status];

  return (
    <article className="ev-detail">
      <div className="ev-back-row">{back}</div>

      <header className="ev-hero">
        <EventImage src={event.image_url} title={event.title} className="ev-hero__img" iconSize={64} />
        <div className="ev-hero__shade" />
        <div className="ev-hero__content">
          <div className="ev-hero__badges">
            <Tag>{startCase(event.event_type)}</Tag>
            <Tag tone="neutral">{formatFormat(event)}</Tag>
            {event.status && event.status !== 'upcoming' && <Tag tone={event.status === 'ongoing' ? 'success' : event.status === 'cancelled' ? 'danger' : 'warning'}>{status}</Tag>}
          </div>
          <h1>{event.title}</h1>
          <div className="ev-hero__facts">
            <span><CalendarClock size={16} aria-hidden="true" /> {formatDateRange(event.start_date, event.end_date)}</span>
            <span><MapPin size={16} aria-hidden="true" /> {formatLocation(event)}</span>
          </div>
          {cats.length > 0 && (
            <div className="ev-hero__cats">
              {cats.map((c) => <span className="ev-chip ev-chip--light" key={c}>{c}</span>)}
            </div>
          )}
        </div>
      </header>

      <div className="ev-detail__grid">
        <div className="stack">
          <Section icon={FileText} title="About this event">
            {event.description ? <div className="ev-prose">{event.description}</div> : event.summary ? <p className="field-value">{event.summary}</p> : <p className="field-value muted">No description has been provided.</p>}
          </Section>

          <Section icon={CalendarClock} title="Date & time">
            <div className="ev-facts">
              <Fact icon={CalendarClock} label={sameDay ? 'Date' : 'Starts'}>{formatLongDate(event.start_date) || 'To be announced'}</Fact>
              {!sameDay && event.end_date && <Fact icon={CalendarClock} label="Ends">{formatLongDate(event.end_date)}</Fact>}
              <Fact icon={Video} label="Time">{timeLine(event)}</Fact>
              {event.timezone && <Fact icon={Sparkles} label="Timezone">{event.timezone}</Fact>}
            </div>
          </Section>

          <LocationSection event={event} />

          {topics.length > 0 && (
            <Section icon={Tags} title="Topics">
              <TagList>{topics.map((t) => <Tag key={t}>{t}</Tag>)}</TagList>
            </Section>
          )}
          {cats.length > 0 && (
            <Section icon={Layers} title="Industries">
              <TagList>{cats.map((c) => <Tag tone="teal" key={c}>{c}</Tag>)}</TagList>
            </Section>
          )}
          {audience.length > 0 && (
            <Section icon={Users} title="Target audience">
              <TagList>{audience.map((a) => <Tag tone="amber" key={a}>{a}</Tag>)}</TagList>
            </Section>
          )}

          <OrganizerCard organizer={event.organizer} />
          <SourceCard event={event} />
        </div>

        <div className="ev-detail__aside">
          <RegistrationCard event={event} />
        </div>
      </div>
    </article>
  );
}
