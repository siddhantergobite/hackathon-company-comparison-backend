import { useState } from 'react';
import { Briefcase, Building2, ChevronDown, Layers, UserRound } from 'lucide-react';
import { Banner, Card, CardHeader, FieldLabel, Tag, TagList } from '../ui';
import { asArray, flattenVal } from '../../utils/data';

function contactLine(contact) {
  if (!contact) return '';
  const parts = [];
  if (contact.name) parts.push(contact.name);
  if (contact.title) parts.push(contact.title);
  if (contact.phone) parts.push(contact.phone);
  if (contact.email) parts.push(contact.email);
  if (contact.source) parts.push(`[${contact.source}${contact.confidence ? ' · ' + contact.confidence : ''}]`);
  return parts.join(' — ');
}

export default function BrochureProfile({ brochure }) {
  const [showVerbatim, setShowVerbatim] = useState(false);
  const words = brochure._meta?.word_count || 0;
  const services = asArray(brochure.services);
  const industries = asArray(brochure.industries);

  return (
    <div className="stack">
      <Banner tone="success" title="Read complete">
        {words} words extracted from the brochure.
      </Banner>

      <Card>
        <CardHeader icon={Building2} title={brochure.company_name || 'Company overview'} />
        <FieldLabel>Summary</FieldLabel>
        <p className="field-value">{flattenVal(brochure.summary) || '—'}</p>
        {brochure.verbatim_extract && (
          <>
            <button
              type="button"
              className="btn btn--ghost btn--sm"
              style={{ marginTop: 10, paddingLeft: 0 }}
              aria-expanded={showVerbatim}
              onClick={() => setShowVerbatim((v) => !v)}
            >
              <ChevronDown
                size={15}
                aria-hidden="true"
                style={{ transform: showVerbatim ? 'rotate(180deg)' : 'none', transition: 'transform .15s' }}
              />
              {showVerbatim ? 'Hide' : 'View'} word-for-word extract
            </button>
            {showVerbatim && (
              <pre className="code-block" style={{ marginTop: 8, maxHeight: 240, overflowY: 'auto' }}>
                {brochure.verbatim_extract}
              </pre>
            )}
          </>
        )}
      </Card>

      <Card>
        <CardHeader icon={Layers} title="Services offered" />
        {services.length ? (
          <TagList>
            {services.map((s, i) => (
              <Tag key={`${s}-${i}`}>{flattenVal(s)}</Tag>
            ))}
          </TagList>
        ) : (
          <p className="field-value muted">—</p>
        )}
      </Card>

      <Card>
        <CardHeader icon={Briefcase} title="Industries served & achievements" />
        <FieldLabel>Industries</FieldLabel>
        <p className="field-value">{industries.map(flattenVal).filter(Boolean).join(', ') || '—'}</p>
        <div style={{ height: 14 }} />
        <FieldLabel>Notable case studies</FieldLabel>
        <p className="field-value">{flattenVal(brochure.case_studies) || '—'}</p>
      </Card>

      <Card>
        <CardHeader icon={UserRound} title="Contact on file" />
        <FieldLabel>Primary contact</FieldLabel>
        <p className="field-value">{contactLine(asArray(brochure.contacts)[0]) || '—'}</p>
      </Card>
    </div>
  );
}
