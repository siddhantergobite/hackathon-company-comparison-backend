import { Link } from 'react-router-dom';
import { CheckCircle2, Circle, Download, FileDown } from 'lucide-react';
import { useCasefile } from '../context/CasefileContext';
import { Banner, Button, Card, PageHeader } from '../components/ui';
import { getTargetName } from '../utils/target';

function Item({ done, title, hint, to, optional }) {
  const Icon = done ? CheckCircle2 : Circle;
  return (
    <li className={done ? 'is-done' : ''}>
      <Icon size={18} className="checklist__mark" aria-hidden="true" />
      <span>
        <strong>{title}</strong>
        {optional && !done && <span className="muted"> (optional)</span>}
        <span className="checklist__hint">
          {done ? 'Included in the PDF' : hint}
          {!done && to && (
            <>
              {' — '}
              <Link to={to}>open</Link>
            </>
          )}
        </span>
      </span>
    </li>
  );
}

export default function ExportPage() {
  const { brochure, target, pitch, aeo, requests, downloadPdf } = useCasefile();
  const { loading, error } = requests.pdf || {};
  const ready = Boolean(brochure && target);

  const title = ready ? `${brochure.company_name || 'Your company'} → ${getTargetName(target)}` : 'Casefile report';
  const parts = ['brochure', 'target intel'];
  if (pitch) parts.push('pitch match', 'outreach draft');
  if (aeo) parts.push('AEO/GEO audit');
  const subtitle = ready
    ? `Branded Casefile PDF — ${parts.join(', ')}.`
    : 'Complete Exhibits A & B, then download.';

  return (
    <>
      <PageHeader
        exhibit="E"
        eyebrow="Export"
        title="Download full casefile"
        description="Export a branded report: cover, KPIs, leadership, hiring, SWOT, pitch match, outreach draft and sources — plus the AEO/GEO audit if you ran Exhibit F."
      />

      <div className="stack stack--lg">
        {error && !loading && (
          <Banner tone="error" title="PDF export failed">
            {error}
          </Banner>
        )}

        <Card flush pad={false} className="export-card">
          <div className="export-card__main">
            <div className="export-card__icon">
              <FileDown size={26} aria-hidden="true" />
            </div>
            <h2 className="export-card__title">{title}</h2>
            <p className="muted" style={{ maxWidth: 480 }}>
              {subtitle}
            </p>
            <Button size="lg" icon={Download} loading={loading} disabled={!ready} onClick={downloadPdf} style={{ marginTop: 10 }}>
              {loading ? 'Building report…' : 'Download PDF'}
            </Button>
          </div>

          <aside className="export-card__side" aria-label="Report contents">
            <div className="field-label" style={{ marginBottom: 14 }}>
              What's included
            </div>
            <ul className="checklist">
              <Item done={Boolean(brochure)} title="Brochure" hint="Required — add it in Exhibit A" to="/brochure" />
              <Item done={Boolean(target)} title="Target intelligence" hint="Required — research a target in Exhibit B" to="/target" />
              <Item done={Boolean(pitch)} title="Pitch match & email draft" hint="Generate in Exhibit C" to="/pitch" optional />
              <Item done={Boolean(aeo)} title="AEO / GEO audit" hint="Run in Exhibit F" to="/aeo-geo" optional />
            </ul>
          </aside>
        </Card>
      </div>
    </>
  );
}
