import { Fragment, useEffect, useState } from 'react';
import { Briefcase, ExternalLink, Link2, Plus, Radar, Trash2, Upload } from 'lucide-react';
import { useToast } from '../context/ToastContext';
import { api } from '../api/client';
import {
  Banner,
  Button,
  Card,
  CardHeader,
  EmptyState,
  KpiGrid,
  LoadingPanel,
  PageHeader,
  Tag,
} from '../components/ui';

const SCAN_STEPS = [
  'Building role + skill queries from each resume',
  'Searching LinkedIn and public Naukri listings with those queries',
  'Keeping posts from the last 30 minutes',
  'Ranking jobs against the talent bench',
];

const URL_STEPS = [
  'Reading the company / job URL',
  'Collecting public LinkedIn, Naukri, and supported career-board listings',
  'Keeping only posts with a verifiable date',
  'Matching the talent bench',
];

function recencyLabel(job) {
  const m = job.posted_minutes;
  if (job.recency === 'date_unverified') return 'Posting date not verified';
  if (m == null || job.recency === 'too_old_or_unknown') {
    if (job.recency === 'too_old_or_unknown') return 'Not within the date window';
    return 'Time not verified';
  }
  if (job.recency === 'posted_in_fallback' && m != null) {
    return `Posted ${m} min ago (1-hour fallback)`;
  }
  if (m < 60) return `Posted ${m} min ago`;
  if (m < 48 * 60) {
    const hrs = Math.max(1, Math.round(m / 60));
    return `Posted ${hrs} hr ago`;
  }
  const days = Math.max(1, Math.round(m / (24 * 60)));
  if (days === 1) return 'Posted yesterday';
  if (days < 14) return `Posted ${days} days ago`;
  return 'Posted about 2 weeks ago';
}

function asJobList(data) {
  if (!data) return [];
  if (Array.isArray(data.jobs)) return data.jobs.filter((j) => j && j.url);
  if (data.url) return [data];
  return [];
}

function externalBoardSearchUrl(board, query) {
  const domains = {
    Indeed: 'indeed.com',
    Glassdoor: 'glassdoor.com',
    Foundit: 'foundit.in',
  };
  const search = `site:${domains[board]} ${query}`;
  return `https://www.google.com/search?q=${encodeURIComponent(search)}`;
}

const MATCH_LEVELS = {
  strong: { label: 'Strong match', tone: 'green' },
  possible: { label: 'Possible match', tone: 'amber' },
  no_strong_match: { label: 'No strong match', tone: 'red' },
  insufficient_evidence: { label: 'No strong match', tone: 'red' },
  needs_resume: { label: 'Add a resume', tone: 'neutral' },
};

export default function LiveJobsPage() {
  const toast = useToast();
  const [bench, setBench] = useState(null);
  const [scan, setScan] = useState(null);
  const [jobUrl, setJobUrl] = useState('');
  const [loadingScan, setLoadingScan] = useState(false);
  const [loadingBench, setLoadingBench] = useState(false);
  const [error, setError] = useState('');
  const [uploading, setUploading] = useState(false);
  const [loadingIngest, setLoadingIngest] = useState(false);

  const jobs = scan?.jobs || [];
  const verifiedJobs = jobs.filter((job) => job.recency !== 'date_unverified');
  const unverifiedJobs = jobs.filter((job) => job.recency === 'date_unverified');
  const displayJobs = [...verifiedJobs, ...unverifiedJobs];
  const people = bench?.people || {};
  const peopleList = Object.values(people).filter((p) => p?.loaded);

  const loadBench = async () => {
    setLoadingBench(true);
    try {
      setBench(await api.talentBench());
    } catch (e) {
      setError(e.message);
    } finally {
      setLoadingBench(false);
    }
  };

  useEffect(() => {
    loadBench();
  }, []);

  const onUpload = async (file, slotId) => {
    if (!file) return;
    setUploading(true);
    try {
      setBench(await api.talentUpload(file, slotId));
      toast.success(slotId ? 'Resume replaced' : 'Resume added');
    } catch (e) {
      toast.error(e.message);
    } finally {
      setUploading(false);
    }
  };

  const onUploadMany = async (files) => {
    const selectedFiles = Array.from(files || []);
    if (!selectedFiles.length) return;

    setUploading(true);
    let updatedBench = bench;
    let added = 0;
    let stoppedAtLimit = false;
    const failures = [];

    try {
      for (const file of selectedFiles) {
        try {
          updatedBench = await api.talentUpload(file);
          added += 1;
        } catch (e) {
          failures.push({ name: file.name, message: e.message });
          if (e.message.toLowerCase().includes('talent bench is full')) {
            stoppedAtLimit = true;
            break;
          }
        }
      }

      if (added > 0) {
        setBench(updatedBench);
        toast.success(`${added} resume${added === 1 ? '' : 's'} added`);
      }

      const notAttempted = stoppedAtLimit
        ? selectedFiles.length - added - failures.length
        : 0;
      if (failures.length || notAttempted > 0) {
        const firstFailure = failures[0];
        const detail = firstFailure ? ` ${firstFailure.name}: ${firstFailure.message}` : '';
        const skipped = notAttempted > 0 ? ` ${notAttempted} remaining file${notAttempted === 1 ? ' was' : 's were'} skipped.` : '';
        toast.error(`Could not add ${failures.length + notAttempted} selected file${failures.length + notAttempted === 1 ? '' : 's'}.${detail}${skipped}`);
      }
    } finally {
      setUploading(false);
    }
  };

  const onClear = async (slotId) => {
    try {
      setBench(await api.talentClear(slotId));
    } catch (e) {
      toast.error(e.message);
    }
  };

  const onScan = async () => {
    const url = jobUrl.trim();
    if (url) {
      await runIngest(url);
      return;
    }
    setLoadingScan(true);
    setError('');
    try {
      setScan(await api.liveJobsScan());
    } catch (e) {
      setError(e.message);
    } finally {
      setLoadingScan(false);
    }
  };

  const runIngest = async (url) => {
    setLoadingIngest(true);
    setError('');
    try {
      const data = await api.liveJobsIngest(url);
      const list = asJobList(data);
      setScan({
        ...(data || {}),
        jobs: list,
        job_count: data.job_count ?? list.length,
        in_window_count: data.in_window_count ?? list.length,
        verified_job_count: data.verified_job_count ?? data.in_window_count ?? list.length,
        unverified_job_count: data.unverified_job_count ?? list.filter((job) => job.recency === 'date_unverified').length,
        window_minutes: data.window_minutes || (data.window_days ? data.window_days * 24 * 60 : 30),
        window_days: data.window_days || 14,
        fallback_used: false,
        bench_loaded: peopleList.length,
        scanned_at: data.scanned_at || new Date().toISOString(),
        _meta: data._meta || { note: 'Jobs from the pasted URL (last 2 weeks, dated posts only).' },
      });
      if (list.length) {
        const dated = data.verified_job_count ?? list.filter((job) => job.recency !== 'date_unverified').length;
        const undated = data.unverified_job_count ?? list.filter((job) => job.recency === 'date_unverified').length;
        toast.success(`${dated} date-verified job${dated === 1 ? '' : 's'}${undated ? `, ${undated} with unverified dates` : ''}`);
      }
    } catch (err) {
      toast.error(err.message);
    } finally {
      setLoadingIngest(false);
    }
  };

  const onIngest = async (e) => {
    e.preventDefault();
    const url = jobUrl.trim();
    if (!url) {
      toast.error('Paste a LinkedIn company page, job post, Naukri/Greenhouse board, or company website');
      return;
    }
    await runIngest(url);
  };

  return (
    <>
      <PageHeader
        exhibit="G"
        eyebrow="Staffing signal"
        title="Live jobs from your talent bench"
        description="Two modes: scan fresh public AI/software posts, or paste a LinkedIn company page, Naukri URL, Greenhouse job board, job post, or company website to find dated jobs from the last 2 weeks. Resume matching is separate from job discovery. We never log in or auto-message recruiters."
      />

      <div className="stack stack--lg">
        <Card>
          <CardHeader icon={Upload} title="Talent bench — add resumes" />
          <p className="form-hint" style={{ marginTop: 0 }}>
            Optional. Select multiple resumes at once (up to 20 total); they upload one by one. If you skip this, scan still finds live AI/software jobs.
          </p>
          <div className="job-actions" style={{ marginBottom: 12 }}>
            <label className="btn btn--sm">
              <Plus size={16} aria-hidden="true" />
              {uploading ? 'Reading resumes…' : 'Add resumes'}
              <input
                type="file"
                accept=".pdf,.docx,.doc,.txt"
                multiple
                hidden
                disabled={uploading}
                onChange={(ev) => {
                  const files = Array.from(ev.target.files || []);
                  ev.target.value = '';
                  if (files.length) onUploadMany(files);
                }}
              />
            </label>
          </div>
          {peopleList.length === 0 ? (
            <p className="form-hint">No resumes yet. Scan last 30 minutes still works. Add resumes when you want skill-matched search.</p>
          ) : (
            <div className="job-bench-grid">
              {peopleList.map((p) => (
                <div className="job-bench-card" key={p.slot}>
                  <strong>{p.name || p.label || p.filename || p.slot}</strong>
                  <p className="form-hint">
                    {p.title || 'Role not parsed'}
                    {p.years_experience ? ` · ${p.years_experience}` : ''}
                    {(p.skills || []).length ? ` · ${(p.skills || []).slice(0, 8).join(', ')}` : ''}
                  </p>
                  <div className="job-actions">
                    <label className="btn btn--ghost btn--sm">
                      Replace
                      <input
                        type="file"
                        accept=".pdf,.docx,.doc,.txt"
                        hidden
                        disabled={uploading}
                        onChange={(ev) => {
                          const file = ev.target.files?.[0];
                          ev.target.value = '';
                          if (file) onUpload(file, p.slot);
                        }}
                      />
                    </label>
                    <Button variant="ghost" size="sm" icon={Trash2} disabled={uploading} onClick={() => onClear(p.slot)}>
                      Remove
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card>
          <form onSubmit={onIngest} className="stack">
            <label className="form-label" htmlFor="job-url">
              Company, Naukri / Greenhouse board, website, or job URL
            </label>
            <div className="input-wrap">
              <Link2 size={17} aria-hidden="true" />
              <input
                id="job-url"
                className="input input--icon"
                value={jobUrl}
                onChange={(e) => setJobUrl(e.target.value)}
                placeholder="LinkedIn company · naukri.com/… · boards.greenhouse.io/company · company website · job URL"
                autoComplete="off"
                spellCheck="false"
              />
            </div>
            <div className="job-actions">
              <Button type="submit" variant="secondary" icon={Link2} loading={loadingIngest}>
                Find last 2 weeks
              </Button>
              <Button type="button" icon={Radar} loading={loadingScan} onClick={onScan}>
                {jobUrl.trim() ? 'Find last 2 weeks' : 'Scan last 30 minutes'}
              </Button>
            </div>
            <p className="form-hint">
              Find last 2 weeks uses the pasted source and keeps verifiably dated posts. Greenhouse boards are checked through their public job-board API. Leave the URL box empty to scan recent live jobs.
            </p>
          </form>
        </Card>

        {error && !loadingScan && (
          <Banner tone="error" title="Live jobs scan failed">
            {error}
          </Banner>
        )}

        {loadingScan && <LoadingPanel title="Scanning public job listings…" steps={SCAN_STEPS} />}
        {loadingIngest && <LoadingPanel title="Finding dated jobs from the last 2 weeks…" steps={URL_STEPS} />}
        {loadingBench && !bench && <LoadingPanel title="Loading talent bench…" steps={['Reading saved resumes']} />}

        {scan && (
          <KpiGrid
            items={[
              ['Date verified', scan.verified_job_count ?? scan.in_window_count ?? verifiedJobs.length],
              ['Date unverified', scan.unverified_job_count ?? unverifiedJobs.length],
              ['Listed', scan.job_count ?? jobs.length],
              ['Search sources', Object.keys(scan.source_diagnostics || {}).length || scan.sources?.length || 0],
              ['Window', scan.window_days
                ? `${scan.window_days} days`
                : scan.fallback_used
                  ? '1 hour fallback'
                  : `${scan.window_minutes || 30} min`],
            ]}
          />
        )}

        {scan?.source_diagnostics && Object.keys(scan.source_diagnostics).length > 0 && (
          <div className="job-bench-grid" aria-label="Search diagnostics">
            {Object.entries(scan.source_diagnostics).map(([source, stats]) => (
              <div className="job-bench-card" key={source}>
                <strong>{source === 'naukri' ? 'Naukri discovery' : source === 'linkedin' ? 'LinkedIn discovery' : source}</strong>
                <p className="form-hint">
                  {stats.queries_attempted ?? stats.naukri_queries ?? 0} search requests · {stats.search_results ?? 0} results · {stats.job_urls_accepted ?? stats.unique_job_urls ?? 0} job URLs · {stats.detail_pages_read ?? 0} detail pages read
                </p>
                {stats.search_providers && Object.keys(stats.search_providers).length > 0 && (
                  <p className="form-hint">
                    Search-provider result rows: {Object.entries(stats.search_providers).map(([provider, count]) => `${provider} (${count})`).join(', ')}
                  </p>
                )}
                <p className="form-hint">
                  {stats.posting_dates_verified ?? 0} dates verified · {stats.date_unverified ?? 0} unverified · {stats.outside_fallback_window ?? stats.outside_window ?? 0} outside date window
                </p>
                {source === 'naukri' && (
                  <p className="form-hint">
                    Showing {stats.displayed_jobs ?? 0} of the 5–8 Naukri target · {Number.isFinite(scan.elapsed_ms) ? `scan took ${(scan.elapsed_ms / 1000).toFixed(1)}s` : 'scan time unavailable'}
                  </p>
                )}
              </div>
            ))}
          </div>
        )}

        {scan && (
          <Card>
            <CardHeader icon={ExternalLink} title="Search other job boards" />
            <p className="form-hint">
              These open public web searches for your resume-based queries. The boards do not provide approved job-search feeds to this app, so these results are not imported or resume-ranked automatically.
            </p>
            <div className="job-bench-grid">
              {['Indeed', 'Glassdoor', 'Foundit'].map((board) => (
                <div className="job-bench-card" key={board}>
                  <strong>{board}</strong>
                  <div className="job-actions" style={{ marginTop: 10 }}>
                    {(scan.search_queries || ['software engineer']).slice(0, 3).map((query) => (
                      <a
                        className="btn btn--ghost btn--sm"
                        href={externalBoardSearchUrl(board, query)}
                        key={`${board}-${query}`}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        {query}
                      </a>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </Card>
        )}

        {!loadingScan && scan && jobs.length === 0 && (
          <EmptyState icon={Briefcase} title="No jobs found">
            {scan?._meta?.note ||
              'Nothing with a verifiable posting date in this window. Days/months-old listings stay hidden.'}
          </EmptyState>
        )}

        {!loadingScan && jobs.length > 0 && (
          <>
            <p className="form-hint">
              Fit compares technical skills detected in the listing text with skills extracted from each resume. Strong means at least 3 detected skills and 70% overlap; Possible means at least one match and 40% overlap. “Not found” means the skill was not extracted from the resume, not that the candidate lacks it. Listing mentions may be preferred rather than required.
            </p>
            <div className="job-card-grid">
              {displayJobs.map((job, index) => (
                <Fragment key={job.id || job.url}>
                {index === verifiedJobs.length && unverifiedJobs.length > 0 && (
                  <div style={{ gridColumn: '1 / -1' }}>
                    <h3 className="card__title">Posting date unverified ({unverifiedJobs.length})</h3>
                    <p className="form-hint">These Naukri results matched a public search, but the posting date could not be confirmed. They are not counted as recent or date-verified.</p>
                  </div>
                )}
              <article className="card job-result-card">
                <div className="job-actions" style={{ marginBottom: 10 }}>
                  <Tag>{job.track || 'role'}</Tag>
                  <Tag>{job.platform || ''}</Tag>
                  {job.recency === 'date_unverified' && <Tag tone="amber">Date unverified</Tag>}
                </div>
                <h3 className="card__title" style={{ margin: '0 0 6px' }}>
                  {job.title || 'Role'}
                </h3>
                <p className="form-hint" style={{ margin: '0 0 10px' }}>
                  {job.company || 'Company not listed'} · {recencyLabel(job)}
                </p>
                {job.description_source ? (
                  <details className="job-description">
                    <summary>View fetched job description used for fit</summary>
                    <p>{job.description || job.snippet}</p>
                  </details>
                ) : job.snippet ? (
                  <p style={{ margin: '0 0 14px', fontSize: 14, lineHeight: 1.5 }}>{job.snippet}</p>
                ) : null}
                {(() => {
                  const evidence = job.match_evidence || {};
                  const level = MATCH_LEVELS[evidence.fit_level] || MATCH_LEVELS.no_strong_match;
                  const candidate = evidence.candidate || job.matched_talent;
                  const listingSkills = evidence.listing_skills || [];
                  const matchedSkills = evidence.matched_skills || [];
                  const missingSkills = evidence.missing_skills || [];
                  return (
                    <div className="job-match">
                      <div className="job-actions">
                        <strong>Resume fit</strong>
                        <Tag tone={level.tone}>{level.label}</Tag>
                        {candidate && (
                          <span className="form-hint">
                            {candidate.basis === 'role_only' ? 'Closest by role only' : 'Best matching resume'}:
                            {' '}{candidate.name || candidate.slot}
                          </span>
                        )}
                      </div>
                      <p className="form-hint">{evidence.reason || 'Run a new scan to assess resume fit.'}</p>
                      {listingSkills.length > 0 ? (
                        <>
                          <p className="form-hint"><strong>Skills mentioned in listing</strong></p>
                          <div className="tag-list">
                            {listingSkills.map((skill) => (
                              <Tag key={skill} tone={matchedSkills.includes(skill) ? 'green' : 'neutral'}>{skill}</Tag>
                            ))}
                          </div>
                          {missingSkills.length > 0 && (
                            <p className="form-hint">
                              <strong>Not found in this resume:</strong> {missingSkills.join(', ')}
                            </p>
                          )}
                        </>
                      ) : null}
                    </div>
                  );
                })()}
                <div className="job-actions">
                  <a className="btn btn--ghost btn--sm" href={job.url} target="_blank" rel="noopener noreferrer">
                    <ExternalLink size={16} aria-hidden="true" />
                    Open post
                  </a>
                </div>
              </article>
                </Fragment>
              ))}
            </div>
          </>
        )}

      </div>
    </>
  );
}
