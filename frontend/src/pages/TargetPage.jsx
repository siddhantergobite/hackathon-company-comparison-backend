import { useMemo } from 'react';
import { ArrowRight, Building2, Globe } from 'lucide-react';
import { useCasefile } from '../context/CasefileContext';
import { useToast } from '../context/ToastContext';
import { Banner, EmptyState, KpiGrid, LinkButton, LoadingPanel, PageHeader, SearchBar } from '../components/ui';
import { buildTargetView } from '../utils/target';
import { TargetHero, SourcesBar } from '../components/target/TargetHero';
import ConfidenceCard from '../components/target/ConfidenceCard';
import SummaryCards from '../components/target/SummaryCards';
import IntelTabs from '../components/target/IntelTabs';
import ConclusionCard from '../components/target/ConclusionCard';
import SourcesCard from '../components/target/SourcesCard';

const RESEARCH_STEPS = [
  'Reading the company website',
  'Checking Wikipedia and Wikidata',
  'Filling missing profile gaps with AI and public evidence',
  'Structuring the report with AI',
  'Reviewing people, competitors, finance, SWOT, and risk claims',
];

function normalizedHost(value) {
  const text = String(value || '').trim();
  if (!text) return '';
  try {
    const withScheme = /^https?:\/\//i.test(text) ? text : `https://${text}`;
    return new URL(withScheme).hostname.toLowerCase().replace(/^www\./, '');
  } catch {
    return '';
  }
}

export default function TargetPage() {
  const { target, targetUrl: url, setTargetUrl, requests, researchTarget, clearTargetResearch } = useCasefile();
  const toast = useToast();
  const { loading, error, startedAt, requestedUrl } = requests.target || {};
  const view = useMemo(() => (target ? buildTargetView(target) : null), [target]);
  const targetHost = normalizedHost(target?._meta?.queried_url || target?._meta?.domain);

  const onUrlChange = (nextValue) => {
    setTargetUrl(nextValue);
    const nextHost = normalizedHost(nextValue);
    const requestHost = normalizedHost(requestedUrl);
    if ((target && nextHost !== targetHost) || (loading && requestHost && nextHost !== requestHost)) {
      clearTargetResearch();
    }
  };

  const onSearch = () => {
    let value = url.trim();
    if (!value) {
      toast.error('Enter a target URL, e.g. https://www.sacpl.co/');
      return;
    }
    if (!value.startsWith('http')) value = 'https://' + value;
    researchTarget(value);
  };

  return (
    <>
      <PageHeader
        exhibit="B"
        eyebrow="Prospect research"
        title="Target company profile"
        description="Search any company to pull a public profile — leadership, point of contact and current hiring — with an AI read on what they're likely building."
        actions={
          view && (
            <LinkButton to="/pitch" icon={ArrowRight}>
              Compare & pitch
            </LinkButton>
          )
        }
      />

      <div className="stack stack--lg">
        <div>
          <SearchBar
            value={url}
            onChange={onUrlChange}
            onSubmit={onSearch}
            placeholder="https://www.sacpl.co/"
            buttonLabel="Research"
            inputIcon={Globe}
            loading={loading}
            label="Target company website"
          />
          <p className="form-hint">Public-source research runs in the background. You can open Live Jobs and return; this search continues.</p>
        </div>

        {error && !loading && (
          <Banner tone="error" title="Research failed">
            {error}
          </Banner>
        )}

        {loading && <LoadingPanel title="Researching target company…" steps={RESEARCH_STEPS} startedAt={startedAt} />}

        {!loading && !view && (
          <EmptyState icon={Building2} title="No target researched yet">
            Enter a company URL above to build a sourced profile with leadership, hiring signals, SWOT and more.
          </EmptyState>
        )}

        {!loading && view && (
          <div className="stack stack--lg">
            <TargetHero view={view} />
            <SourcesBar citations={view.citations} count={view.citationCount} />
            <KpiGrid items={view.kpis} />
            {view.hasConfidence && <ConfidenceCard view={view} />}
            <SummaryCards view={view} />
            <IntelTabs report={target} />
            <ConclusionCard view={view} />
            <SourcesCard citations={view.citations} />
          </div>
        )}
      </div>
    </>
  );
}
