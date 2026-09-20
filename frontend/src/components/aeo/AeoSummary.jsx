import { Card, CardHeader, KpiGrid, ScoreRing, Tag, TagList } from '../ui';
import { asArray, percentScore } from '../../utils/data';
import { ListChecks } from 'lucide-react';

export function AeoHero({ data }) {
  const analysis = data.analysis || {};
  const meta = data._meta || {};
  return (
    <div className="hero">
      <h2 className="hero__title">{data.company_name || data.domain || '—'}</h2>
      <div className="hero__sub">
        {[data.domain, meta.search_engine || 'duckduckgo', `${meta.elapsed_seconds || '?'}s`].filter(Boolean).join(' · ')}
      </div>
      {analysis.visibility_summary && <p className="hero__summary">{analysis.visibility_summary}</p>}
    </div>
  );
}

export function AeoScores({ data }) {
  const analysis = data.analysis || {};
  const geo = data.geo_snapshot || {};
  const aeo = percentScore(analysis.aeo_score);
  const geoScore = percentScore(analysis.geo_score_blended ?? analysis.geo_score);

  return (
    <div className="stack stack--lg">
      <Card pad={false} className="score-pair">
        <div className="score-pair__item">
          <ScoreRing value={aeo} size={88} stroke={9} label={`AEO score ${aeo ?? 'unavailable'}`} />
          <div>
            <div className="score-pair__label">AEO score</div>
            <div className="score-pair__desc">Answer-engine readiness</div>
          </div>
        </div>
        <div className="score-pair__item">
          <ScoreRing value={geoScore} size={88} stroke={9} label={`GEO score ${geoScore ?? 'unavailable'}`} />
          <div>
            <div className="score-pair__label">GEO score</div>
            <div className="score-pair__desc">Generative-engine visibility</div>
          </div>
        </div>
      </Card>
      <KpiGrid
        items={[
          ['Topics', asArray(data.topics).length],
          ['Mentions', geo.mention_count ?? 0],
          ['Fixes', asArray(analysis.recommendations).length],
        ]}
      />
    </div>
  );
}

export function SignalsCard({ data }) {
  const signals = data.on_page?.signals || {};
  const flags = [
    ['H1', signals.has_h1],
    ['Meta description', signals.has_meta_description],
    ['About page', signals.has_about_page],
    ['FAQ schema', signals.has_faq_schema],
    ['Organization schema', signals.has_organization_schema],
  ];
  return (
    <Card>
      <CardHeader icon={ListChecks} title="On-page signals" />
      <TagList>
        {flags.map(([label, on]) => (
          <Tag key={label} tone={on ? 'green' : 'red'}>
            {label}: {on ? 'Yes' : 'No'}
          </Tag>
        ))}
        <Tag tone="neutral">FAQs: {signals.faq_count ?? 0}</Tag>
      </TagList>
    </Card>
  );
}
