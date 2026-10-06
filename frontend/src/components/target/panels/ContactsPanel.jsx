import { Mail, MapPin, Phone, UserRound } from 'lucide-react';
import { CiteBadge } from '../../ui';
import { asArray, hasData, val } from '../../../utils/data';

export default function ContactsPanel({ report }) {
  const co = report.company_profile || {};
  const ci = report.contact_intelligence || {};
  const poc = report.point_of_contact || {};
  const address = ci.registered_address || val(co.registered_address);
  const phones = asArray(ci.phones).filter((p) => p && p.number);
  const emails = asArray(ci.emails).filter((e) => e && e.email);
  const offices = asArray(ci.addresses)
    .map((a) => (typeof a === 'string' ? a : a?.address || a?.value || ''))
    .filter(hasData);

  const hasPoc = hasData(poc.name) || hasData(poc.email) || hasData(poc.phone);

  if (!hasPoc && !hasData(address) && !phones.length && !emails.length && !offices.length) {
    return <p className="field-value muted">No contacts found on public sources</p>;
  }

  return (
    <>
      {hasPoc && (
        <div className="contact-block">
          <strong>
            <UserRound size={15} style={{ verticalAlign: '-2px', marginRight: 6 }} aria-hidden="true" />
            Public point of contact
          </strong>
          <div style={{ marginTop: 4 }}>
            {poc.name && <div><strong>{poc.name}</strong>{poc.title ? ` · ${poc.title}` : ''}</div>}
            {hasData(poc.email) && <div>{poc.email}</div>}
            {hasData(poc.phone) && <div>{poc.phone}</div>}
            {poc.reason && <div className="mini-card__meta">{poc.reason}</div>}
            <CiteBadge field={poc} />
          </div>
        </div>
      )}
      {hasData(address) && (
        <div className="contact-block">
          <strong>
            <MapPin size={15} style={{ verticalAlign: '-2px', marginRight: 6 }} aria-hidden="true" />
            Registered address
          </strong>
          <div style={{ marginTop: 4 }}>
            {address}
            {ci.address_source && <span className="cite-badge">{ci.address_source}</span>}
          </div>
        </div>
      )}

      {phones.length > 0 && (
        <>
          <h4 className="subhead">
            <Phone size={13} style={{ verticalAlign: '-2px', marginRight: 6 }} aria-hidden="true" />
            Phone numbers
          </h4>
          {phones.map((p, i) => (
            <div className="data-row" key={`${p.number}-${i}`}>
              <strong>{p.person_name || p.name || 'Phone'}</strong>: {p.number} <CiteBadge field={p} />
            </div>
          ))}
        </>
      )}

      {emails.length > 0 && (
        <>
          <h4 className="subhead">
            <Mail size={13} style={{ verticalAlign: '-2px', marginRight: 6 }} aria-hidden="true" />
            Email addresses
          </h4>
          {emails.map((e, i) => (
            <div className="data-row" key={`${e.email}-${i}`}>
              <strong>{e.person_name || e.name || e.label || 'Email'}</strong>
              {e.title ? ` (${e.title})` : ''}: {e.email} <CiteBadge field={e} />
            </div>
          ))}
        </>
      )}

      {offices.map((a, i) => (
        <div className="data-row" key={`${a}-${i}`}>
          <strong>Office</strong>: {a}
        </div>
      ))}
    </>
  );
}
