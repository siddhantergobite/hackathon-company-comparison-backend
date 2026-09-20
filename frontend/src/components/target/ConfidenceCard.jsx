import { ShieldCheck } from 'lucide-react';
import { Card, CardHeader, Meter } from '../ui';

export default function ConfidenceCard({ view }) {
  return (
    <Card className="confidence" pad={false}>
      <CardHeader icon={ShieldCheck} title="Data confidence" />
      <div className="confidence__meters">
        <Meter label="Authenticity" value={view.authenticity} />
        <Meter label="Completeness" value={view.completeness} />
        <Meter label="Source reliability" value={view.reliability} />
      </div>
      <div className="confidence__foot">
        {view.citationCount > 0 && (
          <a href="#sources">
            {view.citationCount} source{view.citationCount !== 1 ? 's' : ''}
          </a>
        )}
        {view.generatedAt && <span>Generated: {view.generatedAt}</span>}
        <span>Completeness is not accuracy — overall is capped by authenticity and source reliability.</span>
      </div>
    </Card>
  );
}
