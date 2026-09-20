import { Compass } from 'lucide-react';
import { EmptyState, LinkButton } from '../components/ui';

export default function NotFoundPage() {
  return (
    <div className="not-found">
      <EmptyState
        icon={Compass}
        title="Page not found"
        action={<LinkButton to="/brochure">Back to Exhibit A</LinkButton>}
      >
        That page doesn't exist in this casefile.
      </EmptyState>
    </div>
  );
}
