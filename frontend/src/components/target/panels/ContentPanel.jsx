import { FieldLabel, Tag, TagList } from '../../ui';
import { asArray, hasData, pointOf, val } from '../../../utils/data';

export default function ContentPanel({ report }) {
  const cs = report.content_strategy || {};
  const pillars = asArray(cs.content_pillars).length ? asArray(cs.content_pillars) : asArray(cs.pillars);
  const ideas = asArray(cs.viral_content_ideas).length ? asArray(cs.viral_content_ideas) : asArray(cs.content_ideas);
  const hashtags = asArray(cs.top_hashtags).length ? asArray(cs.top_hashtags) : asArray(cs.hashtags);
  const gap = val(cs.competitor_content_gap || cs.content_gap_opportunity);

  return (
    <>
      <h4 className="subhead">Brand voice</h4>
      <p className="field-value">{val(cs.brand_voice) || 'Professional, clear voice'}</p>

      <h4 className="subhead">Content pillars</h4>
      {pillars.length ? (
        <TagList>
          {pillars.map((p, i) => (
            <Tag key={`${pointOf(p)}-${i}`}>{pointOf(p)}</Tag>
          ))}
        </TagList>
      ) : (
        <p className="field-value muted">—</p>
      )}

      {ideas.length > 0 && (
        <>
          <h4 className="subhead">Viral content ideas</h4>
          <ul style={{ lineHeight: 1.7 }}>
            {ideas.map((idea, i) => (
              <li key={`${pointOf(idea)}-${i}`}>{pointOf(idea)}</li>
            ))}
          </ul>
        </>
      )}

      {hashtags.length > 0 && (
        <>
          <h4 className="subhead">Top hashtags</h4>
          <TagList>
            {hashtags.map((t, i) => (
              <Tag tone="amber" key={`${pointOf(t)}-${i}`}>
                {pointOf(t)}
              </Tag>
            ))}
          </TagList>
        </>
      )}

      {hasData(gap) && (
        <div className="callout" style={{ marginTop: 22 }}>
          <FieldLabel>Content gap</FieldLabel>
          <p className="field-value">{gap}</p>
        </div>
      )}
    </>
  );
}
