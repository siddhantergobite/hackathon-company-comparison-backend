import { useState } from 'react';
import { Globe, Radar, Tags } from 'lucide-react';
import { useCasefile } from '../context/CasefileContext';
import { useToast } from '../context/ToastContext';
import { Banner, Button, Card, EmptyState, LoadingPanel, PageHeader, TabPanel, Tabs } from '../components/ui';
import { AeoHero, AeoScores, SignalsCard } from '../components/aeo/AeoSummary';
import {
  ChecklistSection,
  FaqsSection,
  GapsSection,
  GeoSection,
  RecommendationsSection,
  TopicsSection,
} from '../components/aeo/AeoSections';
import { asArray } from '../utils/data';

const AEO_STEPS = [
  'Crawling on-page structure',
  'Finding who is winning for key topics',
  'Checking external mentions',
  'Generating before/after fixes',
];

const SECTIONS = [
  { id: 'topics', title: 'Who\'s winning', Section: TopicsSection, count: (d) => asArray(d.topic_research).length },
  { id: 'gaps', title: 'Gaps', Section: GapsSection, count: (d) => asArray(d.analysis?.gaps).length },
  { id: 'fixes', title: 'Before / after fixes', Section: RecommendationsSection, count: (d) => asArray(d.analysis?.recommendations).length },
  { id: 'faqs', title: 'Suggested FAQs', Section: FaqsSection, count: (d) => asArray(d.analysis?.suggested_faqs).length },
  { id: 'geo', title: 'GEO snapshot', Section: GeoSection, count: (d) => asArray(d.geo_snapshot?.external_mentions).length },
  { id: 'checklist', title: 'Distribution checklist', Section: ChecklistSection, count: (d) => asArray(d.analysis?.distribution_checklist).length },
];

export default function AeoGeoPage() {
  const { aeo, requests, runAeoAudit } = useCasefile();
  const toast = useToast();
  const [url, setUrl] = useState('');
  const [keywords, setKeywords] = useState('');
  const [tab, setTab] = useState('topics');
  const { loading, error } = requests.aeo || {};

  const submit = (e) => {
    e.preventDefault();
    const target = url.trim();
    if (!target) {
      toast.error('Enter a website URL, e.g. https://www.buffer.com');
      return;
    }
    const list = keywords
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);
    runAeoAudit(target, list.length ? list : null);
  };

  const tabs = SECTIONS.map((s) => ({ id: s.id, label: aeo ? `${s.title} (${s.count(aeo)})` : s.title }));
  const current = SECTIONS.find((s) => s.id === tab) || SECTIONS[0];

  return (
    <>
      <PageHeader
        exhibit="F"
        eyebrow="Visibility audit"
        title="AEO / GEO visibility audit"
        description="Enter a website URL. We crawl on-page structure, find who's winning for key topics, and return before/after fixes for headings, FAQs and schema."
      />

      <div className="stack stack--lg">
        <Card>
          <form onSubmit={submit} className="stack">
            <div>
              <label className="form-label" htmlFor="aeo-url">
                Website URL
              </label>
              <div className="input-wrap">
                <Globe size={17} aria-hidden="true" />
                <input
                  id="aeo-url"
                  className="input input--icon"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="https://www.buffer.com"
                  disabled={loading}
                  autoComplete="off"
                  spellCheck="false"
                />
              </div>
            </div>
            <div>
              <label className="form-label" htmlFor="aeo-keywords">
                Topics <span className="muted" style={{ fontWeight: 400 }}>(optional)</span>
              </label>
              <div className="input-wrap">
                <Tags size={17} aria-hidden="true" />
                <input
                  id="aeo-keywords"
                  className="input input--icon"
                  value={keywords}
                  onChange={(e) => setKeywords(e.target.value)}
                  placeholder="Comma-separated — leave blank to auto-suggest"
                  disabled={loading}
                  autoComplete="off"
                />
              </div>
              <p className="form-hint">
                Uses DuckDuckGo by default — no Groq key needed; Azure OpenAI is used when the LLM is required. Audits take 30–90 seconds.
              </p>
            </div>
            <div>
              <Button type="submit" icon={Radar} loading={loading}>
                Run audit
              </Button>
            </div>
          </form>
        </Card>

        {error && !loading && (
          <Banner tone="error" title="AEO / GEO audit failed">
            {error} — check the backend on :8765 and try again.
          </Banner>
        )}

        {loading && <LoadingPanel title="Running AEO / GEO audit…" steps={AEO_STEPS} />}

        {!loading && !aeo && (
          <EmptyState icon={Radar} title="No audit yet">
            Run an audit to see your answer-engine and generative-engine visibility, plus concrete fixes.
          </EmptyState>
        )}

        {!loading && aeo && (
          <div className="stack stack--lg">
            <AeoHero data={aeo} />
            <AeoScores data={aeo} />
            <SignalsCard data={aeo} />
            <div>
              <Tabs tabs={tabs} value={tab} onChange={setTab} idPrefix="aeo" label="Audit sections" />
              <TabPanel idPrefix="aeo" id={current.id}>
                <current.Section data={aeo} />
              </TabPanel>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
