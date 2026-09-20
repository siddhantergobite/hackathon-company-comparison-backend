import { UserRound } from 'lucide-react';
import { Card, CardHeader, FieldLabel } from '../ui';
import { hasData } from '../../utils/data';

const FIELDS = [
  ['Name', 'name'],
  ['Title', 'title'],
  ['Company', 'company'],
  ['Email', 'email'],
  ['Phone', 'phone'],
];

export default function PocCard({ poc }) {
  return (
    <Card>
      <CardHeader icon={UserRound} title="Point of contact" />
      {poc ? (
        FIELDS.map(([label, key]) => (
          <div className="poc-row" key={key}>
            <FieldLabel>{label}</FieldLabel>
            <div className="poc-row__value">{hasData(poc[key]) ? poc[key] : '—'}</div>
          </div>
        ))
      ) : (
        <p className="field-value muted">Complete Exhibit B first.</p>
      )}
    </Card>
  );
}
