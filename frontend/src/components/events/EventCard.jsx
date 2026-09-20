import { Link } from 'react-router-dom';
import { ArrowRight, Building2, CalendarDays, MapPin } from 'lucide-react';
import { Tag } from '../ui';
import EventImage from './EventImage';
import { formatDateRange, formatFormat, formatLocation, formatPrice, startCase } from '../../utils/events';

export default function EventCard({ event, typeLabels = {} }) {
  const price = formatPrice(event.registration);
  const loc = event.location || {};
  const cats = (event.categories?.length ? event.categories : event.topics) || [];
  const fmt = formatFormat(event);

  return (
    <article className="ev-card">
      <div className="ev-card__media">
        <EventImage src={event.image_url} title={event.title} />
        <div className="ev-card__badges">
          {event.status === 'ongoing' && <Tag tone="success">Happening now</Tag>}
          {event.status === 'postponed' && <Tag tone="warning">Postponed</Tag>}
          {event.status === 'cancelled' && <Tag tone="danger">Cancelled</Tag>}
          {price === 'Free' && <Tag tone="teal">Free</Tag>}
        </div>
      </div>

      <div className="ev-card__body">
        <div className="ev-card__meta">
          <span className="ev-card__type">{typeLabels[event.event_type] || startCase(event.event_type) || 'Event'}</span>
          <span className="ev-card__format">{fmt}</span>
        </div>

        <h3 className="ev-card__title">
          <Link to={`/events/${event.slug}`} className="ev-card__link">
            {event.title}
          </Link>
        </h3>

        <ul className="ev-card__facts">
          <li>
            <CalendarDays size={15} aria-hidden="true" />
            <span>{formatDateRange(event.start_date, event.end_date)}</span>
          </li>
          <li>
            <MapPin size={15} aria-hidden="true" />
            <span>
              {formatLocation(event)}
              {loc.venue && event.format !== 'online' ? ` · ${loc.venue}` : ''}
            </span>
          </li>
          {event.organizer?.name && (
            <li>
              <Building2 size={15} aria-hidden="true" />
              <span>{event.organizer.name}</span>
            </li>
          )}
        </ul>

        {cats.length > 0 && (
          <div className="ev-card__cats" aria-label="Categories">
            {cats.slice(0, 3).map((c) => (
              <span className="ev-chip" key={c}>
                {c}
              </span>
            ))}
            {cats.length > 3 && <span className="ev-chip ev-chip--more">+{cats.length - 3}</span>}
          </div>
        )}

        {event.summary && <p className="ev-card__summary">{event.summary}</p>}

        <div className="ev-card__foot">
          {price && price !== 'Free' ? <span className="ev-card__price">From {price}</span> : <span />}
          <span className="ev-card__cta" aria-hidden="true">
            View Details <ArrowRight size={16} />
          </span>
        </div>
      </div>
    </article>
  );
}

export function EventCardSkeleton() {
  return (
    <div className="ev-card ev-card--skeleton" aria-hidden="true">
      <div className="ev-card__media skeleton" />
      <div className="ev-card__body">
        <div className="skeleton skeleton--line" style={{ width: '40%' }} />
        <div className="skeleton skeleton--title" />
        <div className="skeleton skeleton--line" style={{ width: '70%' }} />
        <div className="skeleton skeleton--line" style={{ width: '55%' }} />
        <div className="skeleton skeleton--line" style={{ width: '90%', marginTop: 8 }} />
        <div className="skeleton skeleton--line" style={{ width: '80%' }} />
      </div>
    </div>
  );
}
