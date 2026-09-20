import { useState } from 'react';
import { Check, Copy } from 'lucide-react';
import { Button, Card } from '../ui';
import { htmlToText, sanitizeHtml } from '../../utils/html';
import { flattenVal } from '../../utils/data';
import { useToast } from '../../context/ToastContext';

function address(name, email) {
  const n = flattenVal(name);
  const e = flattenVal(email);
  if (!n && !e) return '—';
  return e ? `${n} <${e}>`.trim() : n;
}

// Read-only preview of the generated outreach email. `actions` renders in the footer.
export default function EmailDraft({ email = {}, actions }) {
  const [copied, setCopied] = useState(false);
  const toast = useToast();
  const html = email.body_html ? sanitizeHtml(email.body_html) : '';
  const plain = html ? '' : flattenVal(email.body);

  const copy = async () => {
    const text = `Subject: ${email.subject || ''}\n\n${html ? htmlToText(email.body_html) : plain}`;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error('Could not copy to the clipboard.');
    }
  };

  return (
    <Card flush pad={false} className="email">
      <dl className="email__meta" style={{ margin: 0 }}>
        <div className="email__row">
          <dt>To</dt>
          <dd>{address(email.to_name, email.to_email)}</dd>
        </div>
        <div className="email__row">
          <dt>From</dt>
          <dd>{address(email.from_name, email.from_email)}</dd>
        </div>
        <div className="email__row">
          <dt>Subject</dt>
          <dd style={{ fontWeight: 600 }}>{flattenVal(email.subject) || '—'}</dd>
        </div>
      </dl>

      {html ? (
        <div className="email__body" dangerouslySetInnerHTML={{ __html: html }} />
      ) : (
        <div className="email__body email__body--plain">{plain || '—'}</div>
      )}

      <div className="email__actions">
        <Button variant="secondary" size="sm" icon={copied ? Check : Copy} onClick={copy}>
          {copied ? 'Copied' : 'Copy email'}
        </Button>
        {actions}
      </div>
    </Card>
  );
}
