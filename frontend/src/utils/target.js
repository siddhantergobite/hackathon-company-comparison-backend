import { asArray, flattenVal, hasData, isJunkText, scoreNum, val } from './data';

export function getTargetName(target) {
  return target?._meta?.company_name || val(target?.company_profile?.name) || 'Target';
}

// Best point of contact for outreach: supplied POC → named contact email → current executive.
export function bestPoc(report) {
  const supplied = report.point_of_contact;
  if (supplied && (supplied.name || supplied.email || supplied.phone)) {
    return {
      name: supplied.name || '',
      title: supplied.title || '',
      email: supplied.email || '',
      phone: supplied.phone || '',
      company: supplied.company || '',
      reason: supplied.reason || '',
    };
  }
  const co = report.company_profile || {};
  const meta = report._meta || {};
  const company = meta.company_name || val(co.name) || 'Company';
  const contacts = report.contact_intelligence || {};
  const emails = asArray(contacts.emails);
  const phones = asArray(contacts.phones);

  let name = '';
  let title = '';
  let email = '';
  let phone = '';

  const namedEmail =
    emails.find((e) => typeof e === 'object' && e && hasData(e.person_name || e.person || e.name)) ||
    emails[0];

  if (namedEmail) {
    if (typeof namedEmail === 'string') {
      email = namedEmail;
    } else {
      name = namedEmail.person_name || namedEmail.person || namedEmail.name || '';
      title = namedEmail.title || namedEmail.label || namedEmail.role || '';
      email = namedEmail.email || namedEmail.address || '';
    }
  }

  const firstName = name.split(/\s+/)[0]?.toLowerCase() || '';
  const matchedPhone =
    phones.find((p) => {
      if (typeof p !== 'object' || !p) return false;
      const pn = (p.person_name || p.name || '').toLowerCase();
      return firstName && pn.includes(firstName);
    }) || phones[0];

  if (matchedPhone) {
    phone = typeof matchedPhone === 'string' ? matchedPhone : matchedPhone.number || '';
    if (!name && typeof matchedPhone === 'object') {
      name = matchedPhone.person_name || matchedPhone.name || '';
    }
  }

  if (!name && !email) {
    const leaders = asArray(report.leadership_team).filter((l) => l && l.name);
    const current = leaders.filter((l) => l.status !== 'historical');
    const exec =
      current.find((l) => /ceo|chief executive|managing director|\bmd\b|president/i.test(l.role || '')) ||
      current.find((l) => /cfo|coo|cto|chair/i.test(l.role || '')) ||
      current[0];
    if (exec) {
      name = exec.name || '';
      title = exec.role || exec.title || '';
    }
  }

  return { name, title, email, phone, company, reason: '' };
}

// Everything the Target page needs, derived once from the raw research report.
export function buildTargetView(report) {
  const co = report.company_profile || {};
  const meta = report._meta || {};
  const sc = report.intelligence_score || {};

  const name = getTargetName(report);
  const industry = val(co.industry);
  const hqRaw = val(co.headquarters);
  const hq = hasData(hqRaw) ? hqRaw : '';
  const description = val(co.description);
  const overall = scoreNum(sc.overall);
  const completeness = scoreNum(sc.data_completeness);
  const reliability = scoreNum(sc.source_reliability);
  const authenticity = scoreNum(sc.authenticity);

  const summaryText = flattenVal(sc.summary);
  const heroSummary =
    (!isJunkText(description) && description) || (!isJunkText(summaryText) && summaryText) || '';

  const employees =
    val(co.employee_count) || val(co.employees) || val((report.employee_insights || {}).total_employees);

  const kpis = [
    ['Founded', val(co.founded)],
    ['Employees', employees],
    ['Revenue', val(co.annual_revenue)],
    ['HQ', hq],
    ['Score', overall != null ? `${overall}/100` : ''],
  ].filter(([, v]) => hasData(v));

  const citations = asArray(meta.citations).filter((c) => c && (c.url || c.domain));

  return {
    name,
    heroTitle: name + (hq ? ' • ' + hq.split(',')[0] : ''),
    heroSub: [industry, val(co.founded)].filter(hasData).join(' · ') || meta.domain || '',
    heroSummary,
    conclusion: flattenVal(report.ai_conclusion) || summaryText || heroSummary || '—',
    overall,
    completeness,
    reliability,
    authenticity,
    kpis,
    citations,
    citationCount: meta.citation_count || citations.length,
    generatedAt: meta.generated_at || '',
    hasConfidence:
      completeness != null || reliability != null || authenticity != null || Boolean(meta.generated_at),
    leaders: asArray(report.leadership_team).filter((l) => l && l.name),
    hiring: asArray(report.hiring_signals).filter((h) => h && h.role),
    signals: asArray(report.signals_used).length
      ? asArray(report.signals_used)
      : asArray(report.hiring_signals),
    poc: bestPoc(report),
  };
}
