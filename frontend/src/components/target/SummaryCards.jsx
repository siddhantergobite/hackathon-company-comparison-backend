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
  const visibleLeaders = leaders.filter((leader) => leader?.verification_status !== 'model-knowledge-reviewed');
  const visiblePoc = poc?.verification_status === 'model-knowledge-reviewed' ? {} : poc;
  const hasPoc = visiblePoc.name || visiblePoc.email || visiblePoc.phone;

  return (
    <div className="grid-3">
      <MiniCard icon={Users} title="Leadership">
        {visibleLeaders.length ? (
          visibleLeaders.slice(0, 4).map((l, i) => (
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
        title={visiblePoc.verification_status === 'search-snippet-supported'
          ? 'Search result contact lead'
          : 'Point of contact'}
      >
        {hasPoc ? (
          <>
            {visiblePoc.name && <Person name={visiblePoc.name} role={visiblePoc.title} />}
            {hasData(visiblePoc.email) && <div className="mini-card__meta">{visiblePoc.email}</div>}
            {hasData(visiblePoc.phone) && <div className="mini-card__meta">{visiblePoc.phone}</div>}
            {visiblePoc.reason && <div className="mini-card__meta">{visiblePoc.reason}</div>}
            {visiblePoc.verification_status === 'search-snippet-supported' && (
              <div className="mini-card__meta">Found in a search snippet; linked page was not fetched</div>
            )}
            {visiblePoc.verification_status === 'evidence-verified' && (
              <div className="mini-card__meta">Evidence verified</div>
            )}
            {(visiblePoc.source || visiblePoc.confidence) && (
              <div className="mini-card__meta">{[visiblePoc.source, visiblePoc.confidence].filter(Boolean).join(' · ')}</div>
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
