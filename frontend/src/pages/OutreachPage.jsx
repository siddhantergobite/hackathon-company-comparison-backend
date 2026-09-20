import { useMemo } from 'react';
import { Send, Sparkles } from 'lucide-react';
import { useCasefile } from '../context/CasefileContext';
import { useToast } from '../context/ToastContext';
import { Button, EmptyState, LinkButton, PageHeader } from '../components/ui';
import EmailDraft from '../components/pitch/EmailDraft';
import PocCard from '../components/outreach/PocCard';
import OutreachLog from '../components/outreach/OutreachLog';
import { bestPoc, getTargetName } from '../utils/target';

export default function OutreachPage() {
  const { target, pitch, outreachLog, logOutreach } = useCasefile();
  const toast = useToast();
  const basePoc = useMemo(() => (target ? bestPoc(target) : null), [target]);
  const email = pitch?.email_draft;

  // The pitch email's recipient wins over the researched contact when both exist.
  const poc = useMemo(() => {
    if (!basePoc) return null;
    if (!email) return basePoc;
    return {
      name: email.to_name || basePoc.name,
      title: basePoc.title,
      email: email.to_email || basePoc.email,
      phone: basePoc.phone,
      company: basePoc.company || getTargetName(target),
    };
  }, [basePoc, email, target]);

  const send = () => {
    if (!pitch) return;
    logOutreach({
      id: Date.now(),
      company: basePoc?.company || getTargetName(target),
      contact: email?.to_name || basePoc?.name || '—',
      date: new Date().toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }),
      status: 'Sent',
    });
    toast.info('Email logged (demo — no mail server configured).');
  };

  return (
    <>
      <PageHeader
        exhibit="D"
        eyebrow="Outreach"
        title="Send to point of contact"
        description="Review the final draft and send it to the target company's point of contact. Delivery is logged for follow-up."
      />

      <div className="stack stack--lg">
        <div className="grid-aside">
          {pitch ? (
            <EmailDraft
              email={email}
              actions={
                <Button icon={Send} onClick={send}>
                  Send email
                </Button>
              }
            />
          ) : (
            <EmptyState
              icon={Sparkles}
              title="No draft to send yet"
              action={<LinkButton to="/pitch">Go to Compare & Pitch</LinkButton>}
            >
              Generate a pitch in Exhibit C first — the email draft will appear here for review.
            </EmptyState>
          )}
          <PocCard poc={poc} />
        </div>

        <OutreachLog entries={outreachLog} />
      </div>
    </>
  );
}
