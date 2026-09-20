import { Lightbulb } from 'lucide-react';
import { Card, CardHeader, FieldLabel, Tag, TagList } from '../ui';
import { flattenVal } from '../../utils/data';

export default function ConclusionCard({ view }) {
  const signals = view.signals
    .slice(0, 6)
    .map((s) => (typeof s === 'object' ? s.role : s))
    .map((s) => flattenVal(s))
    .filter(Boolean);

  return (
    <Card accent>
      <CardHeader icon={Lightbulb} title="AI conclusion" />
      <p style={{ fontSize: 16, lineHeight: 1.65 }}>{view.conclusion}</p>
      {signals.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <FieldLabel>Signals used</FieldLabel>
          <TagList>
            {signals.map((s, i) => (
              <Tag tone="amber" key={`${s}-${i}`}>
                {s}
              </Tag>
            ))}
          </TagList>
        </div>
      )}
    </Card>
  );
}
