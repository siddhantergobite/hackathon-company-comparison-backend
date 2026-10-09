import { Briefcase, Gauge, UserCheck, Users } from 'lucide-react';
import { Card, LeaderPerson, Person, ScoreRing } from '../ui';
import { ensureUrl, hasData } from '../../utils/data';

function MiniCard({ icon: Icon, title, children }) {
  return (
    <Card className="mini-card" pad={false}>
      <div className="mini-card__head">
        <Icon size={15} aria-hidden="true" />
        {title}
      </div>
      {children}
    </Card>
  );
}

export default function SummaryCards({ view }) {
  const { leaders, hiring, poc, overall } = view;
  const hasPoc = poc.name || poc.email || poc.phone;

  return (
    <div className="grid-3">
      <MiniCard icon={Users} title="Leadership">
        {leaders.length ? (
          leaders.slice(0, 4).map((l, i) => (
            <div key={`${l.name}-${i}`}>
              <LeaderPerson leader={l} />
              <div className="mini-card__meta">
                {[l.role, l.source, l.confidence].filter(Boolean).join(' · ')}
              </div>
            </div>
          ))
        ) : (
          <span className="field-value muted">No public leadership found</span>
        )}
      </MiniCard>

      <MiniCard icon={Briefcase} title="Current hiring">
        {hiring.length ? (
          hiring.slice(0, 3).map((h, i) => (
            <div className="hiring-item" key={`${h.role}-${i}`}>
              {h.source_url ? (
                <a href={ensureUrl(h.source_url)} target="_blank" rel="noopener noreferrer">
                  {h.role}
                </a>
              ) : (
                <span className="hiring-item__role">{h.role}</span>
              )}
              <div className="mini-card__meta">{h.platform || 'Official'}</div>
            </div>
          ))
        ) : (
          <span className="field-value muted">No public hiring found</span>
        )}
      </MiniCard>

      <MiniCard
        icon={UserCheck}
        title={poc.verification_status === 'model-knowledge-reviewed'
          ? 'Suggested executive'
          : poc.verification_status === 'search-snippet-supported'
            ? 'Search result contact lead'
            : 'Point of contact'}
      >
        {hasPoc ? (
          <>
            {poc.name && <Person name={poc.name} role={poc.title} />}
            {hasData(poc.email) && <div className="mini-card__meta">{poc.email}</div>}
            {hasData(poc.phone) && <div className="mini-card__meta">{poc.phone}</div>}
            {poc.reason && <div className="mini-card__meta">{poc.reason}</div>}
            {poc.verification_status === 'model-knowledge-reviewed' && (
              <div className="mini-card__meta">AI knowledge only - not verified as a direct company contact</div>
            )}
            {poc.verification_status === 'search-snippet-supported' && (
              <div className="mini-card__meta">Found in a search snippet; linked page was not fetched</div>
            )}
            {poc.verification_status === 'evidence-verified' && (
              <div className="mini-card__meta">Evidence verified</div>
            )}
            {(poc.source || poc.confidence) && (
              <div className="mini-card__meta">{[poc.source, poc.confidence].filter(Boolean).join(' · ')}</div>
            )}
          </>
        ) : (
          <span className="field-value muted">No current operating contact verified on public sources</span>
        )}
      </MiniCard>

      <MiniCard icon={Gauge} title="Intelligence score">
        <div className="row" style={{ gap: 16 }}>
          <ScoreRing value={overall} label={overall != null ? `Overall score ${overall} out of 100` : 'Score unavailable'} />
          <div>
            <div style={{ fontWeight: 700, fontSize: 15 }}>{overall != null ? `${overall}/100 overall` : '—'}</div>
            <div className="mini-card__meta">Capped by source reliability</div>
          </div>
        </div>
      </MiniCard>
    </div>
  );
}
