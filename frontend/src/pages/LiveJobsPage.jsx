import { Fragment, useEffect, useRef, useState } from 'react';
import { Briefcase, ChevronDown, ExternalLink, Link2, Plus, Radar, Trash2, Upload } from 'lucide-react';
import { useToast } from '../context/ToastContext';
import { api } from '../api/client';
import TagInput from '../components/ui/TagInput';
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

const MAX_LIVE_SCAN_SKILLS = 5;
const STREAM_BATCH_SIZE = 5;
const LIVE_JOB_LOCATIONS = [
  { id: 'india', label: 'India' },
  { id: 'uk', label: 'UK' },
  { id: 'usa', label: 'USA' },
  { id: 'dubai', label: 'Dubai' },
  { id: 'uae', label: 'UAE' },
  { id: 'singapore', label: 'Singapore' },
  { id: 'canada', label: 'Canada' },
  { id: 'australia', label: 'Australia' },
  { id: 'germany', label: 'Germany' },
  { id: 'netherlands', label: 'Netherlands' },
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

function mergeJobRows(existing, incoming) {
  const rows = new Map();
  [...(existing || []), ...(incoming || [])].forEach((job) => {
    if (!job?.url) return;
    rows.set(job.id || job.url, job);
  });
  return Array.from(rows.values());
}

function normalizeIngestResult(data, peopleCount) {
  const list = asJobList(data);
  return {
    ...(data || {}),
    jobs: list,
    job_count: data?.job_count ?? list.length,
    in_window_count: data?.in_window_count ?? list.length,
    verified_job_count: data?.verified_job_count ?? data?.in_window_count ?? list.length,
    unverified_job_count: data?.unverified_job_count ?? list.filter((job) => job.recency === 'date_unverified').length,
    window_minutes: data?.window_minutes || (data?.window_days ? data.window_days * 24 * 60 : 30),
    window_days: data?.window_days || 14,
    fallback_used: false,
    bench_loaded: peopleCount,
    scanned_at: data?.scanned_at || new Date().toISOString(),
    _meta: data?._meta || { note: 'Jobs from the pasted URL (last 2 weeks, dated posts only).' },
  };
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
  const [liveScanSkills, setLiveScanSkills] = useState([]);
  const [liveScanLocations, setLiveScanLocations] = useState([]);
  const [streamProgress, setStreamProgress] = useState({ received: 0, total: null, batch: 0, phase: '' });
  const streamAbortRef = useRef(null);
  const streamRunIdRef = useRef(0);

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

  useEffect(() => () => streamAbortRef.current?.abort(), []);

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

  const runJobStream = async (mode, request) => {
    streamAbortRef.current?.abort();
    const controller = new AbortController();
    streamAbortRef.current = controller;
    const runId = ++streamRunIdRef.current;
    const isScan = mode === 'scan';
    const setLoading = isScan ? setLoadingScan : setLoadingIngest;

    setScan(null);
    setError('');
    setStreamProgress({ received: 0, total: null, batch: 0, phase: '' });
    setLoading(true);

    const onEvent = (event) => {
      if (runId !== streamRunIdRef.current) return;
      if (event.type === 'batch') {
        setScan((current) => {
          const summary = event.summary || {};
          const jobsNow = mergeJobRows(current?.jobs, event.jobs);
          return {
            ...(current || {}),
            ...summary,
            jobs: jobsNow,
            job_count: event.total_jobs ?? summary.job_count ?? jobsNow.length,
            _meta: { ...(current?._meta || {}), ...(summary._meta || {}) },
          };
        });
        setStreamProgress((current) => ({
          ...current,
          received: event.received_jobs ?? current.received,
          total: event.total_jobs ?? current.total,
          batch: event.batch_index ?? current.batch,
          phase: event.phase || current.phase,
        }));
      } else if (event.type === 'complete') {
        const result = isScan ? event.result : normalizeIngestResult(event.result, peopleList.length);
        setScan(result);
        setStreamProgress((current) => ({
          ...current,
          received: result?.jobs?.length || 0,
          total: result?.jobs?.length || 0,
          phase: 'complete',
        }));
      }
    };

    try {
      const result = await request(onEvent, controller.signal);
      if (mode === 'ingest' && runId === streamRunIdRef.current) {
        const data = normalizeIngestResult(result, peopleList.length);
        const list = data.jobs;
        if (list.length) {
          const dated = data.verified_job_count ?? list.filter((job) => job.recency !== 'date_unverified').length;
          const undated = data.unverified_job_count ?? list.filter((job) => job.recency === 'date_unverified').length;
          toast.success(`${dated} date-verified job${dated === 1 ? '' : 's'}${undated ? `, ${undated} with unverified dates` : ''}`);
        }
      }
      return result;
    } catch (err) {
      if (err?.name !== 'AbortError' && runId === streamRunIdRef.current) {
        setError(err.message);
        if (mode === 'ingest') toast.error(err.message);
      }
      return null;
    } finally {
      if (runId === streamRunIdRef.current) {
        setLoading(false);
        streamAbortRef.current = null;
      }
    }
  };

  const onScan = async () => {
    const url = jobUrl.trim();
    if (url) {
      await runIngest(url);
      return;
    }
    await runJobStream(
      'scan',
      (onEvent, signal) => api.liveJobsScanStream({
        skills: liveScanSkills,
        locations: liveScanLocations,
      }, onEvent, signal),
    );
  };

  const runIngest = async (url) => runJobStream(
    'ingest',
    (onEvent, signal) => api.liveJobsIngestStream(url, onEvent, signal),
  );

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
        description="Two modes: scan fresh public AI/software posts, or paste a LinkedIn company page, Naukri URL, Greenhouse job board, job post, or company website to find dated jobs from the last 2 weeks. Live scans can be narrowed to up to five skills and selected locations. Resume matching is separate from job discovery. We never log in or auto-message recruiters."
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
          <CardHeader icon={Radar} title="Live scan filters" />
          <p className="form-hint" style={{ marginTop: 0 }}>
            Optional filters for the <strong>Scan last 30 minutes</strong> search. A job must mention at least one selected skill and one selected location when those filters are used. Company-link searches remain unchanged.
          </p>
          <div className="job-filter-grid">
            <div>
              <label className="form-label" htmlFor="live-job-skills">Skills (up to 5)</label>
              <TagInput
                id="live-job-skills"
                value={liveScanSkills}
                onChange={(next) => setLiveScanSkills(next.slice(0, MAX_LIVE_SCAN_SKILLS))}
                placeholder="Python, Java, AI/ML…"
                label="Live job skills"
              />
              <p className="form-hint">
                Press Enter or type a comma after each skill. {liveScanSkills.length}/{MAX_LIVE_SCAN_SKILLS} added.
              </p>
            </div>
            <div>
              <span className="form-label" id="live-job-locations-label">Job locations</span>
              <details className="job-location-picker">
                <summary className="input job-location-summary" aria-labelledby="live-job-locations-label">
                  <span>
                    {liveScanLocations.length
                      ? `${liveScanLocations.length} location${liveScanLocations.length === 1 ? '' : 's'} selected`
                      : 'Any location'}
                  </span>
                  <ChevronDown size={17} aria-hidden="true" />
                </summary>
                <div className="job-location-menu">
                  {LIVE_JOB_LOCATIONS.map((location) => (
                    <label className="job-location-option" key={location.id}>
                      <input
                        type="checkbox"
                        checked={liveScanLocations.includes(location.id)}
                        onChange={() => {
                          setLiveScanLocations((current) => current.includes(location.id)
                            ? current.filter((id) => id !== location.id)
                            : [...current, location.id]);
                        }}
                      />
                      <span>{location.label}</span>
                    </label>
                  ))}
                </div>
              </details>
              <p className="form-hint">Select one or more locations. Leave empty to search all locations.</p>
            </div>
          </div>
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
              Results arrive in groups of 5, up to 20 exact public listings. Find last 2 weeks uses the pasted source and keeps verifiably dated posts. Greenhouse boards are checked through their public job-board API. Leave the URL box empty to scan recent live jobs. If fewer listings pass the date/source checks, none are invented.
            </p>
          </form>
        </Card>

        {error && !loadingScan && !loadingIngest && (
          <Banner tone="error" title="Live jobs request failed">
            {error}
          </Banner>
        )}

        {(loadingScan || loadingIngest) && streamProgress.received > 0 && (
          <Banner tone="info" title="Live results are arriving">
            Showing {streamProgress.received}{streamProgress.total ? ` of ${streamProgress.total}` : ''} result{streamProgress.received === 1 ? '' : 's'} now. New verified results are released in batches of {STREAM_BATCH_SIZE}.
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
                <p className="form-hint">
                  {stats.filtered_by_skill ?? 0} filtered by skill · {stats.filtered_by_location ?? 0} filtered by selected location
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

        {jobs.length > 0 && (
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
