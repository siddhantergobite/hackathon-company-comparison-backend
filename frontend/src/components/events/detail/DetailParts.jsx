import { ExternalLink, Globe, Link2, MapPin, ShieldCheck, Ticket } from 'lucide-react';
import { Card, CardHeader, Tag, TagList } from '../../ui';
import { formatIsoDate, formatPrice, osmEmbedUrl, osmLink, safeUrl } from '../../../utils/events';

export function Section({ icon, title, children }) {
  return (
    <Card as="section">
      <CardHeader icon={icon} title={title} />
      {children}
    </Card>
  );
}

export function Fact({ icon: Icon, label, children }) {
  return (
    <div className="ev-fact">
      <span className="ev-fact__icon">
        <Icon size={18} aria-hidden="true" />
      </span>
      <div>
        <div className="ev-fact__label">{label}</div>
        <div className="ev-fact__value">{children}</div>
      </div>
    </div>
  );
}

export function LocationSection({ event }) {
  const loc = event.location || {};
  const lines = [loc.venue, loc.address, [loc.city, loc.state].filter(Boolean).join(', '), loc.country].filter(Boolean);
  const hasCoords = typeof loc.latitude === 'number' && typeof loc.longitude === 'number';
  const online = event.format === 'online' || (event.is_online && !lines.length);

  return (
    <Section icon={MapPin} title="Location">
      {online && <p className="field-value">This is an online event — join from anywhere. Access details are provided on registration.</p>}
      {lines.length > 0 && (
        <address className="ev-address">
          {lines.map((l, i) => (
            <div key={i} className={i === 0 && loc.venue ? 'ev-address__venue' : ''}>
              {l}
            </div>
          ))}
        </address>
      )}
      {event.format === 'hybrid' && <p className="text-sm muted" style={{ marginTop: 8 }}>Hybrid: attend in person or online.</p>}
      {!online && !lines.length && <p className="field-value muted">Location to be announced.</p>}
      {hasCoords && (
        <div className="ev-map">
          <iframe title={`Map showing ${loc.venue || loc.city || 'the event location'}`} src={osmEmbedUrl(loc.latitude, loc.longitude)} loading="lazy" referrerPolicy="no-referrer" />
          <a className="text-sm" href={osmLink(loc.latitude, loc.longitude)} target="_blank" rel="noopener noreferrer">
            View larger map <ExternalLink size={12} aria-hidden="true" />
          </a>
        </div>
      )}
    </Section>
  );
}

export function OrganizerCard({ organizer = {} }) {
  const site = safeUrl(organizer.website);
  const social = Object.entries(organizer.social_links || {}).filter(([, u]) => safeUrl(u));
  if (!organizer.name && !organizer.description && !site && !social.length) return null;
  return (
    <Section icon={Globe} title="Organizer">
      {organizer.name && <div className="ev-org__name">{organizer.name}</div>}
      {organizer.description && <p className="field-value" style={{ marginTop: 6 }}>{organizer.description}</p>}
      {(site || social.length > 0) && (
        <div className="ev-org__links">
          {site && (
            <a className="btn btn--secondary btn--sm" href={site} target="_blank" rel="noopener noreferrer">
              <Globe size={14} aria-hidden="true" /> Website
            </a>
          )}
          {social.map(([name, url]) => (
            <a key={name} className="btn btn--secondary btn--sm" href={safeUrl(url)} target="_blank" rel="noopener noreferrer">
              <Link2 size={14} aria-hidden="true" /> {name.charAt(0).toUpperCase() + name.slice(1)}
            </a>
          ))}
        </div>
      )}
    </Section>
  );
}

export function RegistrationCard({ event }) {
  const reg = event.registration || {};
  const official = safeUrl(event.event_url) || safeUrl(reg.url);
  const registerUrl = safeUrl(reg.url);
  const price = formatPrice(reg);
  const cancelled = event.status === 'cancelled';

  return (
    <Card className="ev-reg" as="aside" aria-label="Registration">
      <div className="ev-reg__head">
        <Ticket size={18} aria-hidden="true" />
        <h2>Registration</h2>
      </div>

      <div className="ev-reg__price">
        {price ? (
          <>
            <span className="ev-reg__amount">{price}</span>
            {reg.ticket_type && <Tag tone={reg.ticket_type === 'free' ? 'teal' : 'neutral'}>{reg.ticket_type === 'free' ? 'Free' : 'Paid'}</Tag>}
          </>
        ) : (
          <span className="muted">Pricing not listed</span>
        )}
      </div>
      {reg.currency && reg.ticket_type === 'paid' && <div className="text-sm muted">Currency: {reg.currency}</div>}
      {reg.ticket_info && <p className="text-sm" style={{ marginTop: 10 }}>{reg.ticket_info}</p>}

      {cancelled && <p className="text-sm con" style={{ marginTop: 10 }}>This event has been cancelled.</p>}
      {event.status === 'postponed' && <p className="text-sm" style={{ marginTop: 10, color: 'var(--warning)' }}>This event has been postponed. Check the official site for new dates.</p>}

      <div className="ev-reg__actions">
        {official ? (
          <a className="btn btn--primary btn--lg" href={official} target="_blank" rel="noopener noreferrer">
            Visit Official Event Website <ExternalLink size={16} aria-hidden="true" />
          </a>
        ) : (
          <p className="text-sm muted">No official website has been listed for this event.</p>
        )}
        {registerUrl && registerUrl !== official && (
          <a className="btn btn--secondary" href={registerUrl} target="_blank" rel="noopener noreferrer">
            Register <ExternalLink size={14} aria-hidden="true" />
          </a>
        )}
      </div>
    </Card>
  );
}

export function SourceCard({ event }) {
  const src = event.source || {};
  const url = safeUrl(src.url);
  const others = (event.other_sources || []).filter((s) => s.name);
  if (!src.name && !event.last_verified) return null;
  return (
    <Section icon={ShieldCheck} title="Source">
      <div className="ev-source">
        {src.name && (
          <div>
            <span className="muted">Source: </span>
            {url ? (
              <a href={url} target="_blank" rel="noopener noreferrer">
                {src.name} <ExternalLink size={12} aria-hidden="true" />
              </a>
            ) : (
              <strong>{src.name}</strong>
            )}
          </div>
        )}
        {event.last_verified && (
          <div>
            <span className="muted">Last verified: </span>
            <strong>{formatIsoDate(event.last_verified)}</strong>
          </div>
        )}
        {others.length > 0 && (
          <div>
            <span className="muted">Also listed on: </span>
            <TagList>
              {others.map((s, i) => (
                <Tag tone="neutral" key={`${s.name}-${i}`}>
                  {s.name}
                </Tag>
              ))}
            </TagList>
          </div>
        )}
      </div>
    </Section>
  );
}
