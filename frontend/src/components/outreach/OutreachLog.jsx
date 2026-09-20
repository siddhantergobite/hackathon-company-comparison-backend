import { History } from 'lucide-react';
import { Card, CardHeader, Tag } from '../ui';

export default function OutreachLog({ entries }) {
  return (
    <Card flush pad={false}>
      <div style={{ padding: '20px 24px 0' }}>
        <CardHeader icon={History} title="Outreach log" />
      </div>
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>Company</th>
              <th>Point of contact</th>
              <th>Sent</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {entries.length ? (
              entries.map((e) => (
                <tr key={e.id}>
                  <td>{e.company}</td>
                  <td>{e.contact}</td>
                  <td>{e.date}</td>
                  <td>
                    <Tag tone="green">{e.status}</Tag>
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={4} className="muted">
                  No emails sent yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
