import { Briefcase, Building2, CalendarDays, Download, FileText, Globe2, Newspaper, Send, Settings2, ShieldCheck, Sparkles } from 'lucide-react';

// One entry per exhibit. `isDone` drives the progress ticks in the sidebar.
export const WORKFLOW = [
  {
    path: '/brochure',
    exhibit: 'A',
    title: 'Brochure',
    hint: 'Your company profile',
    icon: FileText,
    isDone: (s) => Boolean(s.brochure),
  },
  {
    path: '/target',
    exhibit: 'B',
    title: 'Target Company',
    hint: 'Research a prospect',
    icon: Building2,
    isDone: (s) => Boolean(s.target),
  },
  {
    path: '/pitch',
    exhibit: 'C',
    title: 'Compare & Pitch',
    hint: 'Fit analysis + email',
    icon: Sparkles,
    isDone: (s) => Boolean(s.pitch),
  },
  {
    path: '/outreach',
    exhibit: 'D',
    title: 'Outreach',
    hint: 'Send to the contact',
    icon: Send,
    isDone: (s) => s.outreachLog.length > 0,
  },
  {
    path: '/export',
    exhibit: 'E',
    title: 'Download PDF',
    hint: 'Full casefile export',
    icon: Download,
    isDone: () => false,
  },
];

export const TOOLS = [
  {
    path: '/aeo-geo',
    exhibit: 'F',
    title: 'AEO / GEO Audit',
    hint: 'Answer-engine visibility',
    icon: Globe2,
    isDone: (s) => Boolean(s.aeo),
  },
  {
    path: '/live-jobs',
    exhibit: 'G',
    title: 'Live Jobs',
    hint: 'AI & software roles, last 30 min',
    icon: Briefcase,
    isDone: () => false,
  },
];

// Event Hub: a separate tool (not part of the exhibit workflow), so no exhibit letter.
export const EVENT_HUB = [
  { path: '/events', title: 'Events', hint: 'Discover upcoming events', icon: CalendarDays, isDone: () => false },
  { path: '/admin', title: 'Event Admin', hint: 'Manage, approve & merge', icon: ShieldCheck, isDone: () => false },
];

// News Intelligence: aggregated headlines with AI summaries, plus source management.
export const NEWS_HUB = [
  { path: '/news', title: 'News', hint: 'Live headlines & stories', icon: Newspaper, isDone: () => false },
  { path: '/news-admin', title: 'News Admin', hint: 'Sources, categories & health', icon: Settings2, isDone: () => false },
];

export const ALL_PAGES = [...WORKFLOW, ...TOOLS, ...EVENT_HUB, ...NEWS_HUB];

// Longest matching path wins, so "/news-admin" is never mistaken for "/news".
export function findPage(pathname) {
  const hit = (p) => pathname === p.path || pathname.startsWith(`${p.path}/`);
  return ALL_PAGES.filter(hit).sort((a, b) => b.path.length - a.path.length)[0];
}
