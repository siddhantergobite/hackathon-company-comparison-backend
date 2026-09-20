import { ArrowRight, Sparkles } from 'lucide-react';
import { useCasefile } from '../context/CasefileContext';
import { Banner, Button, EmptyState, LinkButton, LoadingPanel, PageHeader, Prerequisite } from '../components/ui';
import MatchSummary from '../components/pitch/MatchSummary';
import EmailDraft from '../components/pitch/EmailDraft';
import { getTargetName } from '../utils/target';

export default function PitchPage() {
  const { brochure, target, pitch, requests, generatePitch } = useCasefile();
  const { loading, error } = requests.pitch || {};
  const ready = Boolean(brochure && target);

  return (
    <>
      <PageHeader
        exhibit="C"
        eyebrow="Fit analysis"
        title="Compare & generate pitch"
        description="Your services against the target's needs — generates a match score, a gap analysis and a ready-to-send email draft."
        actions={
          <Button icon={Sparkles} loading={loading} disabled={!ready} onClick={generatePitch}>
            {pitch ? 'Regenerate pitch' : 'Generate pitch'}
          </Button>
        }
      />

      <div className="stack stack--lg">
        <Prerequisite
          items={[
            { done: Boolean(brochure), to: '/brochure', label: 'Exhibit A — Brochure', reason: 'Add your company brochure (Exhibit A).' },
            { done: Boolean(target), to: '/target', label: 'Exhibit B — Target', reason: 'Research a target company (Exhibit B).' },
          ]}
        />

        {error && !loading && (
          <Banner tone="error" title="Pitch generation failed">
            {error}
          </Banner>
        )}

        {loading && (
          <LoadingPanel
            title="Generating pitch…"
            steps={['Comparing your services with their needs', 'Scoring the fit', 'Drafting the outreach email']}
          />
        )}

        {!loading && pitch && (
          <>
            <MatchSummary
              pitch={pitch}
              pitcherName={brochure?.company_name || 'You'}
              targetName={getTargetName(target)}
            />
            <EmailDraft
              email={pitch.email_draft}
              actions={
                <LinkButton to="/outreach" size="sm" icon={ArrowRight}>
                  Continue to outreach
                </LinkButton>
              }
            />
          </>
        )}

        {!loading && !pitch && ready && (
          <EmptyState icon={Sparkles} title="Ready to generate">
            Both exhibits are complete. Generate the pitch to see the fit analysis and email draft.
          </EmptyState>
        )}
      </div>
    </>
  );
}
