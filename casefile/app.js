/* Casefile — wired to FastAPI backend on port 8765 */
const API = (window.location.port === '8765')
  ? window.location.origin
  : `${window.location.protocol}//${window.location.hostname}:8765`;

const state = { brochure: null, target: null, pitch: null, outreachLog: [], aeo: null };

function showView(id, btn) {
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  if (btn) btn.classList.add('active');
  if (id === 'v4') syncOutreach();
}

function toggleVerbatim(id) {
  document.getElementById(id).classList.toggle('open');
}

function showIntelTab(id, btn) {
  document.querySelectorAll('.intel-panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.intel-tab').forEach(b => b.classList.remove('active'));
  document.getElementById(id)?.classList.add('active');
  if (btn) btn.classList.add('active');
}

function val(field) {
  if (field && typeof field === 'object' && 'value' in field) return field.value || '';
  return field || '';
}

function esc(s) {
  const d = document.createElement('div');
  d.textContent = s || '';
  return d.innerHTML;
}

function initials(name) {
  return (name || '?').split(/\s+/).map(w => w[0]).join('').slice(0, 2).toUpperCase();
}

function hasData(v) {
  if (!v) return false;
  const s = String(v).trim().toLowerCase();
  return s && !s.includes('not publicly') && !s.includes('not available') && s !== 'n/a' && s !== '—';
}

function ensureUrl(u) {
  if (!u) return '#';
  u = String(u).trim();
  if (u.startsWith('http://') || u.startsWith('https://')) return u;
  return 'https://' + u.replace(/^\/\//, '');
}

function pointOf(item) {
  if (!item) return '';
  if (typeof item === 'string') return item;
  return item.point || item.value || item.name || item.title || item.item || '';
}

function citeBadge(field) {
  if (!field || typeof field !== 'object') return '';
  const src = field.source || '';
  const conf = field.confidence || '';
  let html = '';
  if (src && hasData(src)) html += `<span class="cite-badge">${esc(src)}</span>`;
  if (conf) html += `<span class="cite-badge conf-${String(conf).toLowerCase()}">● ${esc(conf)}</span>`;
  return html;
}

function intelRow(label, field) {
  const v = typeof field === 'object' ? val(field) : field;
  if (!hasData(v)) return '';
  return `<div class="intel-row"><span style="color:var(--text-muted);font-weight:600;">${esc(label)}:</span> ${esc(v)}${typeof field === 'object' ? citeBadge(field) : ''}</div>`;
}

function riskText(field) {
  if (!field) return '';
  if (typeof field === 'string') return field;
  if (Array.isArray(field)) {
    return field.map(item => {
      if (typeof item === 'string') return item;
      return item.risk || item.point || item.value || '';
    }).filter(Boolean).join('; ');
  }
  if (typeof field === 'object') return field.risk || field.point || field.value || '';
  return String(field);
}

function riskRows(risk) {
  const rows = [
    ['Overall Risk Level', risk.overall_risk_level],
    ['Regulatory Risks', risk.regulatory_risks],
    ['Competitive Risks', risk.competitive_risks],
    ['Operational Risks', risk.operational_risks],
    ['Reputational Risks', risk.reputational_risks],
  ];
  return rows.map(([label, field]) => {
    const v = riskText(field);
    if (!hasData(v)) return '';
    return `<div class="intel-row"><span style="color:var(--text-muted);font-weight:600;">${esc(label)}:</span> ${esc(v)}${typeof field === 'object' && !Array.isArray(field) ? citeBadge(field) : ''}</div>`;
  }).join('');
}

function leaderCard(ldr) {
  const name = ldr.name || 'Unknown';
  const role = ldr.role || ldr.title || '';
  return (
    `<div class="who">
      <div class="avatar">${esc(initials(name))}</div>
      <div>
        <div class="field-value" style="font-weight:500;">${esc(name)}</div>
        <div style="font-size:12px;color:var(--teal);">${esc(role)}</div>
      </div>
    </div>`
  );
}

function bestPoc(report) {
  const co = report.company_profile || {};
  const meta = report._meta || {};
  const company = meta.company_name || val(co.name) || 'Company';
  const contacts = report.contact_intelligence || {};
  const emails = contacts.emails || [];
  const phones = contacts.phones || [];

  let name = '';
  let title = '';
  let email = '';
  let phone = '';

  const namedEmail = emails.find(e => {
    if (typeof e !== 'object') return false;
    return hasData(e.person_name || e.name);
  }) || emails[0];

  if (namedEmail) {
    if (typeof namedEmail === 'string') {
      email = namedEmail;
    } else {
      name = namedEmail.person_name || namedEmail.name || '';
      title = namedEmail.title || namedEmail.label || namedEmail.role || '';
      email = namedEmail.email || namedEmail.address || '';
    }
  }

  const firstName = name.split(/\s+/)[0]?.toLowerCase() || '';
  const matchedPhone = phones.find(p => {
    if (typeof p !== 'object') return false;
    const pn = (p.person_name || p.name || '').toLowerCase();
    return firstName && pn.includes(firstName);
  }) || phones[0];

  if (matchedPhone) {
    phone = typeof matchedPhone === 'string' ? matchedPhone : (matchedPhone.number || '');
    if (!name && typeof matchedPhone === 'object') {
      name = matchedPhone.person_name || matchedPhone.name || '';
    }
  }

  if (!name && !email) {
    const leaders = (report.leadership_team || []).filter(l => l && l.name);
    const exec = leaders.find(l => /ceo|founder|director|head|president|md|managing/i.test(l.role || '')) || leaders[0];
    if (exec) {
      name = exec.name || '';
      title = exec.role || exec.title || '';
    }
  }

  return { name, title, email, phone, company };
}

function renderCitations(meta) {
  const citations = meta.citations || [];
  const bar = document.getElementById('citations-bar');
  const cards = document.getElementById('citation-cards');
  const stack = document.getElementById('citation-stack');
  const countLabel = document.getElementById('citation-count-label');
  const list = document.getElementById('citation-list');

  if (!citations.length) {
    if (bar) bar.style.display = 'none';
    if (cards) cards.style.display = 'none';
    return;
  }

  if (bar) bar.style.display = 'flex';
  if (cards) cards.style.display = 'block';
  if (countLabel) countLabel.textContent = `${citations.length} source${citations.length !== 1 ? 's' : ''}`;

  if (stack) {
    stack.innerHTML = citations.slice(0, 4).map((c, i) => {
      const fav = c.favicon || `https://www.google.com/s2/favicons?domain=${encodeURIComponent(c.domain || '')}&sz=64`;
      return `<img src="${esc(fav)}" alt="" style="left:${i * 14}px" onerror="this.style.display='none'">`;
    }).join('');
  }

  if (list) {
    list.innerHTML = citations.map((c, i) =>
      `<div class="citation-card">
        <span class="cite-badge">${i + 1}</span>
        <div>
          <a href="${esc(ensureUrl(c.url))}" target="_blank" rel="noopener">${esc(c.title || c.domain || 'Source')}</a>
          <div style="font-size:11px;color:var(--text-muted);margin-top:2px;">${esc(c.domain || '')}${c.category ? ' · ' + esc(c.category) : ''}</div>
        </div>
      </div>`
    ).join('');
  }
}

function renderRegistryBlock(reg) {
  if (!reg) return '';
  const conf = reg.confidence || 'Low';
  const confClass = conf === 'High' ? 'conf-high' : conf === 'Medium' ? 'conf-med' : 'conf-low';

  if (conf === 'Low' && reg.message) {
    const alts = (reg.alternatives || []).map(a =>
      `<div class="intel-row" style="font-size:12px;color:var(--text-muted);">
        ${esc(a.legal_name || 'Unknown')} (score ${a.score || 0})
      </div>`
    ).join('');
    return `
      <div class="contact-block" style="margin-bottom:18px;border-color:#e8c4a0;">
        <strong>⚠ MCA entity not verified</strong>
        <span class="cite-badge ${confClass}" style="margin-left:8px;">● ${esc(conf)} confidence</span>
        <div style="margin-top:8px;font-size:13px;">${esc(reg.message)}</div>
        ${reg.match_reason ? `<div style="margin-top:6px;font-size:12px;color:var(--text-muted);">${esc(reg.match_reason)}</div>` : ''}
        ${alts ? `<div style="margin-top:10px;"><b>Other matches found:</b>${alts}</div>` : ''}
      </div>`;
  }

  if (!reg.cin) return '';
  const dirs = (reg.directors || []).map(d =>
    `<div class="intel-row">
      <strong>${esc(d.name)}</strong> — ${esc(d.designation || 'Director')}
      ${d.din ? `<span class="cite-badge">DIN ${esc(d.din)}</span>` : ''}
      <span class="cite-badge ${confClass}">● ${esc(d.confidence || conf)}</span>
      <span class="cite-badge">${esc(d.source || 'ZaubaCorp MCA')}</span>
    </div>`
  ).join('');
  const zaubaLink = reg.url
    ? `<a href="${esc(ensureUrl(reg.url))}" target="_blank" rel="noopener" style="font-size:12px;color:var(--teal);">View on ZaubaCorp ↗</a>`
    : '';
  return `
    <div class="contact-block" style="margin-bottom:18px;">
      <strong>✅ MCA Official Data (via ZaubaCorp)</strong>
      <span class="cite-badge ${confClass}" style="margin-left:8px;">● ${esc(conf)} confidence</span>
      ${reg.legal_name ? `<div style="margin-top:6px;font-size:13px;"><b>Legal entity:</b> ${esc(reg.legal_name)}</div>` : ''}
      ${reg.match_reason ? `<div style="font-size:12px;color:var(--text-muted);margin-top:4px;">${esc(reg.match_reason)}</div>` : ''}
      <div style="margin-top:10px;display:flex;flex-wrap:wrap;gap:8px;">
        ${reg.cin ? `<span class="tag">CIN: ${esc(reg.cin)}</span>` : ''}
        ${reg.status ? `<span class="tag">Status: ${esc(reg.status)}</span>` : ''}
        ${reg.incorporation_date ? `<span class="tag">Incorporated: ${esc(reg.incorporation_date)}</span>` : ''}
        ${reg.authorized_capital ? `<span class="tag">Auth. Capital: ${esc(reg.authorized_capital)}</span>` : ''}
        ${reg.paid_up_capital ? `<span class="tag">Paid-up: ${esc(reg.paid_up_capital)}</span>` : ''}
      </div>
      ${reg.registered_address ? `<div style="margin-top:10px;font-size:13px;"><b>Registered Address:</b> ${esc(reg.registered_address)}</div>` : ''}
      ${reg.email ? `<div style="margin-top:6px;font-size:13px;"><b>MCA Email:</b> ${esc(reg.email)} <span class="cite-badge ${confClass}">● ${esc(conf)}</span></div>` : ''}
      <div style="margin-top:8px;">${zaubaLink}</div>
    </div>
    ${dirs ? `<h4 style="margin-top:14px;">Directors (MCA Registry)</h4>${dirs}` : ''}`;
}

function renderIntelPanels(report) {
  const co = report.company_profile || {};
  const prod = report.products_services || {};
  const mkt = report.market_analysis || {};
  const tech = report.tech_stack || {};
  const emp = report.employee_insights || {};
  const swot = report.swot_analysis || {};
  const cs = report.content_strategy || {};
  const risk = report.risk_assessment || {};
  const fin = report.financial_data || {};
  const ci = report.contact_intelligence || {};

  const offerings = (prod.primary_offerings || prod.value || []).map(o => {
    const name = pointOf(o);
    return name ? `<span class="tag">${esc(name)}</span>` : '';
  }).join('');

  document.getElementById('intel-overview').innerHTML = `
    ${renderRegistryBlock(report.registry_intelligence)}
    <h4>Products &amp; Services</h4>
    ${offerings || '<p class="field-value">—</p>'}
    ${intelRow('Target Customers', prod.target_customers)}
    ${intelRow('Pricing Model', prod.pricing_model)}
    <h4 style="margin-top:18px;">Market Position</h4>
    ${intelRow('Market Position', mkt.market_position)}
    ${intelRow('Geographic Reach', mkt.geographic_reach)}
    <h4 style="margin-top:18px;">Website Technology</h4>
    ${intelRow('Website CMS', tech.website_cms || tech.cms)}
    <p style="font-size:12px;color:var(--text-muted);margin-top:8px;">Detected from homepage HTML/scripts</p>`;

  const comps = (report.competitors || []).filter(c => {
    const n = (c.name || '').toLowerCase();
    return n && !/^competitor\s*\d/i.test(n);
  });
  document.getElementById('intel-competitors').innerHTML = comps.length
    ? comps.map(c => `<div class="competitor-card">
        <div style="display:flex;justify-content:space-between;align-items:center;">
          <strong>${esc(c.name || '')}</strong>
          ${c.threat_level ? `<span class="tag red">${esc(c.threat_level)} threat</span>` : ''}
        </div>
        <div style="font-size:12.5px;color:var(--text-muted);margin:4px 0;">${esc(c.description || '')}</div>
        ${c.strengths ? `<div style="font-size:12px;color:#059669;"><b>Their Edge:</b> ${esc(typeof c.strengths === 'string' ? c.strengths : JSON.stringify(c.strengths))}</div>` : ''}
        ${c.weaknesses ? `<div style="font-size:12px;color:#dc2626;"><b>Their Weakness:</b> ${esc(typeof c.weaknesses === 'string' ? c.weaknesses : JSON.stringify(c.weaknesses))}</div>` : ''}
      </div>`).join('')
    : '<p class="field-value" style="color:var(--text-muted);">No competitor data found</p>';

  const leaders = report.leadership_team || [];
  const leaderHtml = leaders.length
    ? leaders.map(l => `
        <div class="intel-row">
          ${leaderCard(l)}
          ${l.din ? `<span class="cite-badge">DIN ${esc(l.din)}</span>` : ''}
          <span class="cite-badge">${esc(l.source || 'Public source')}</span>
          <span class="cite-badge conf-${(l.confidence || 'medium').toLowerCase()}">● ${esc(l.confidence || 'Medium')}</span>
          ${l.background ? `<div style="font-size:12px;color:var(--text-muted);margin-top:4px;">${esc(l.background)}</div>` : ''}
        </div>`).join('')
    : '<p class="field-value">No public leadership found</p>';

  document.getElementById('intel-people').innerHTML = `
    <h4>Workforce Stats</h4>
    ${intelRow('Total Employees', emp.total_employees || co.employee_count)}
    ${intelRow('Hiring Trend', emp.hiring_trend)}
    ${intelRow('Remote Policy', emp.remote_policy)}
    ${intelRow('Glassdoor Rating', emp.glassdoor_rating)}
    <h4 style="margin-top:18px;">Leadership &amp; Directors</h4>
    ${leaderHtml}
    <h4 style="margin-top:18px;">Culture</h4>
    <p class="field-value" style="font-style:italic;">${esc(val(emp.culture_summary) || 'Limited public culture reviews found')}</p>`;

  const news = report.recent_news || [];
  document.getElementById('intel-news').innerHTML = news.length
    ? news.map(n => `<div class="intel-row">
        <strong>${esc(n.title || '')}</strong>
        ${n.sentiment ? `<span class="tag">${esc(n.sentiment)}</span>` : ''}
        <div style="font-size:12px;color:var(--text-muted);margin-top:4px;">${esc(n.summary || n.date || '')}</div>
      </div>`).join('')
    : '<p class="field-value" style="color:var(--text-muted);">No recent news found</p>';

  function swotList(items) {
    return (items || []).map(i => {
      const pt = pointOf(i);
      if (!hasData(pt)) return '';
      return `<li>${esc(pt)}${typeof i === 'object' ? citeBadge(i) : ''}</li>`;
    }).join('');
  }
  document.getElementById('intel-swot').innerHTML = `
    <div class="swot-grid">
      <div class="swot-box swot-s"><h5>Strengths</h5><ul>${swotList(swot.strengths) || '<li>—</li>'}</ul></div>
      <div class="swot-box swot-w"><h5>Weaknesses</h5><ul>${swotList(swot.weaknesses) || '<li>—</li>'}</ul></div>
      <div class="swot-box swot-o"><h5>Opportunities</h5><ul>${swotList(swot.opportunities) || '<li>—</li>'}</ul></div>
      <div class="swot-box swot-t"><h5>Threats</h5><ul>${swotList(swot.threats) || '<li>—</li>'}</ul></div>
    </div>`;

  const pillars = (cs.content_pillars || cs.pillars || []).map(p => `<span class="tag">${esc(pointOf(p))}</span>`).join('');
  const ideas = (cs.viral_content_ideas || cs.content_ideas || []).map(i => `<li>${esc(pointOf(i))}</li>`).join('');
  const tags = (cs.top_hashtags || cs.hashtags || []).map(t => `<span class="tag amber">${esc(pointOf(t))}</span>`).join('');
  document.getElementById('intel-content').innerHTML = `
    <h4>Brand Voice</h4><p class="field-value">${esc(val(cs.brand_voice) || 'Professional, clear voice')}</p>
    <h4 style="margin-top:14px;">Content Pillars</h4>${pillars || '—'}
    ${ideas ? `<h4 style="margin-top:14px;">Viral Content Ideas</h4><ul>${ideas}</ul>` : ''}
    ${tags ? `<h4 style="margin-top:14px;">Top Hashtags</h4>${tags}` : ''}
    ${hasData(val(cs.competitor_content_gap || cs.content_gap_opportunity)) ? `<div class="analysis-box" style="margin-top:14px;"><span class="field-label">Content Gap</span><p>${esc(val(cs.competitor_content_gap || cs.content_gap_opportunity))}</p></div>` : ''}`;

  document.getElementById('intel-risk').innerHTML = `
    <h4>Financial Intelligence</h4>
    ${intelRow('Revenue Estimate', fin.revenue_estimate)}
    ${intelRow('Funding', fin.funding_status || fin.total_funding)}
    <h4 style="margin-top:18px;">Risk Assessment</h4>
    ${riskRows(risk) || '<p class="field-value">—</p>'}`;

  let contactHtml = '';
  const addr = ci.registered_address || val(co.registered_address);
  if (hasData(addr)) {
    contactHtml += `<div class="contact-block"><strong>📍 Registered Address</strong><br>${esc(addr)}
      ${ci.address_source ? `<br><span class="cite-badge">${esc(ci.address_source)}</span>` : ''}</div>`;
  }
  if (ci.phones?.length) {
    contactHtml += '<h4 style="margin-top:14px;">📞 Phone Numbers</h4>';
    ci.phones.forEach(p => {
      if (p.number) contactHtml += `<div class="intel-row"><strong>${esc(p.person_name || p.name || 'Phone')}</strong>: ${esc(p.number)} ${citeBadge(p)}</div>`;
    });
  }
  if (ci.emails?.length) {
    contactHtml += '<h4 style="margin-top:14px;">✉ Email Addresses</h4>';
    ci.emails.forEach(e => {
      if (e.email) contactHtml += `<div class="intel-row"><strong>${esc(e.person_name || e.name || e.label || 'Email')}</strong>${e.title ? ' (' + esc(e.title) + ')' : ''}: ${esc(e.email)} ${citeBadge(e)}</div>`;
    });
  }
  (ci.addresses || []).forEach(a => {
    const av = typeof a === 'string' ? a : (a.address || a.value || '');
    if (hasData(av)) contactHtml += `<div class="intel-row"><strong>Office</strong>: ${esc(av)}</div>`;
  });
  document.getElementById('intel-contacts').innerHTML = contactHtml || '<p class="field-value" style="color:var(--text-muted);">No contacts found on public sources</p>';
}

function renderBrochure(data) {
  state.brochure = data;
  const meta = data._meta || {};
  document.getElementById('workspace-name').textContent = data.company_name || 'Your Company';
  document.getElementById('brochure-summary').textContent = data.summary || '—';
  document.getElementById('vb1').textContent = data.verbatim_extract || '';
  document.getElementById('brochure-services').innerHTML = (data.services || [])
    .map(s => `<span class="tag">${esc(s)}</span>`).join('') || '<span class="tag">—</span>';
  document.getElementById('brochure-industries').textContent = (data.industries || []).join(', ') || '—';
  document.getElementById('brochure-cases').textContent = data.case_studies || '—';
  const c = (data.contacts || [])[0];
  const parts = [];
  if (c) {
    if (c.name) parts.push(c.name);
    if (c.title) parts.push(c.title);
    if (c.phone) parts.push(c.phone);
    if (c.email) parts.push(c.email);
    if (c.source) parts.push(`[${c.source}${c.confidence ? ' · ' + c.confidence : ''}]`);
  }
  document.getElementById('brochure-contact').textContent = parts.join(' — ') || '—';
  const st = document.getElementById('brochure-status');
  if (st) {
    st.style.display = 'flex';
    document.getElementById('brochure-status-text').textContent =
      `Read complete — ${meta.word_count || 0} words extracted`;
  }
  const pitchHeader = document.getElementById('pitcher-col-header');
  if (pitchHeader) pitchHeader.textContent = `${data.company_name || 'You'} offer`;
}

async function searchBrochure() {
  const q = document.getElementById('brochure-search-input').value.trim();
  if (!q) return alert('Enter company name or URL (e.g. https://ergobite.com/us/)');
  const loading = document.getElementById('brochure-loading');
  loading.classList.add('show');
  try {
    const r = await fetch(`${API}/api/brochure-search`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ company_name: q }),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || 'Search failed');
    renderBrochure(d);
  } catch (e) {
    alert('Brochure search failed: ' + e.message);
  } finally {
    loading.classList.remove('show');
  }
}

async function uploadBrochure(file) {
  const loading = document.getElementById('brochure-loading');
  loading.classList.add('show');
  try {
    const fd = new FormData();
    fd.append('file', file);
    const r = await fetch(`${API}/api/brochure-upload`, { method: 'POST', body: fd });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || 'Upload failed');
    renderBrochure(d);
  } catch (e) {
    alert('Upload failed: ' + e.message);
  } finally {
    loading.classList.remove('show');
  }
}

async function researchTarget() {
  let url = document.getElementById('target-url-input').value.trim();
  if (!url) return alert('Enter target URL e.g. https://www.sacpl.co/');
  if (!url.startsWith('http')) url = 'https://' + url;

  const loading = document.getElementById('target-loading');
  const empty = document.getElementById('target-empty');
  if (loading) loading.classList.add('show');
  if (empty) empty.style.display = 'none';

  try {
    const r = await fetch(`${API}/api/company-research`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || 'Research failed');
    state.target = d;
    renderTargetSummary(d);
    syncOutreach();
  } catch (e) {
    alert('Target research failed: ' + e.message);
    if (empty) empty.style.display = 'block';
  } finally {
    if (loading) loading.classList.remove('show');
  }
}

function renderTargetSummary(report) {
  const el = document.getElementById('target-content');
  if (!el) return;
  el.style.display = 'block';

  const co = report.company_profile || {};
  const meta = report._meta || {};
  const sc = report.intelligence_score || {};
  const name = meta.company_name || val(co.name) || 'Company';
  const ind = val(co.industry);
  const hq = val(co.headquarters);
  const desc = val(co.description);

  document.getElementById('target-hero-name').textContent = name + (hq ? ' • ' + hq.split(',')[0] : '');
  document.getElementById('target-hero-sub').textContent = [ind, val(co.founded)].filter(hasData).join(' · ') || meta.domain || '';
  document.getElementById('target-hero-summary').textContent = sc.summary || desc || '';

  const targetCol = document.getElementById('target-col-header');
  if (targetCol) targetCol.textContent = `${name} appears to need`;

  document.getElementById('target-conclusion').textContent = report.ai_conclusion || sc.summary || '—';
  document.getElementById('target-signals').innerHTML = (report.signals_used || report.hiring_signals || [])
    .slice(0, 6).map(s => `<span class="tag amber">${esc(typeof s === 'object' ? s.role : s)}</span>`).join('');
  document.getElementById('target-score').textContent = sc.overall ? `${sc.overall}/100 overall` : '—';

  const kpis = [
    ['Founded', val(co.founded)],
    ['Employees', val(co.employee_count) || val((report.employee_insights || {}).total_employees)],
    ['Revenue', val(co.annual_revenue)],
    ['HQ', hq],
    ['Score', sc.overall ? sc.overall + '/100' : ''],
  ].filter(([, v]) => hasData(v));
  document.getElementById('target-kpis').innerHTML = kpis.map(([l, v]) =>
    `<div class="kpi-chip"><div class="lbl">${l}</div><div class="val">${esc(v)}</div></div>`
  ).join('');

  const conf = document.getElementById('target-confidence');
  if (sc.data_completeness || sc.source_reliability || meta.generated_at) {
    conf.style.display = 'flex';
    conf.innerHTML = `<b>DATA CONFIDENCE:</b>
      ${sc.data_completeness ? `<span>Completeness: <strong>${sc.data_completeness}/100</strong></span>` : ''}
      ${sc.source_reliability ? `<span>Source Reliability: <strong>${sc.source_reliability}/100</strong></span>` : ''}
      ${meta.citation_count || (meta.citations || []).length ? `<span>${meta.citation_count || meta.citations.length} sources verified</span>` : ''}
      ${meta.generated_at ? `<span>Generated: ${esc(meta.generated_at)}</span>` : ''}`;
  }

  renderIntelPanels(report);
  renderCitations(meta);

  const leaders = (report.leadership_team || []).filter(l => l && l.name);
  document.getElementById('target-leadership').innerHTML = leaders.length
    ? leaders.slice(0, 3).map(l =>
        leaderCard(l) +
        (l.din ? `<div style="font-size:11px;color:var(--text-muted);">DIN ${esc(l.din)} · ${esc(l.source || 'MCA')} · ${esc(l.confidence || 'High')}</div>` : '')
      ).join('')
    : '<span class="field-value">No public leadership found</span>';

  const poc = bestPoc(report);
  const pocEl = document.getElementById('target-poc');
  if (poc.name || poc.email || poc.phone) {
    pocEl.innerHTML =
      (poc.name ? leaderCard({ name: poc.name, role: poc.title }) : '') +
      (poc.email ? `<div style="font-size:12px;margin-top:8px;color:var(--text-muted);">${esc(poc.email)}</div>` : '') +
      (poc.phone ? `<div style="font-size:12px;margin-top:4px;color:var(--text-muted);">${esc(poc.phone)}</div>` : '');
  } else {
    pocEl.innerHTML = '<span class="field-value">No contact found on public sources</span>';
  }

  const hiring = report.hiring_signals || [];
  document.getElementById('target-hiring').innerHTML = hiring.length
    ? hiring.map(h =>
        `<li><span class="role">${esc(h.role)}</span><span class="count">${h.count || 1} open${h.source_url ? `<span class="hiring-source"><a href="${esc(ensureUrl(h.source_url))}" target="_blank" rel="noopener">source</a></span>` : ''}</span></li>`
      ).join('')
    : '<li><span class="role">No public hiring found</span></li>';

  syncPocCard(poc);
  updatePdfTitle();
}

function syncPocCard(poc) {
  if (!poc) return;
  const set = (id, v) => {
    const el = document.getElementById(id);
    if (el) el.textContent = hasData(v) ? v : '—';
  };
  set('poc-name', poc.name);
  set('poc-title', poc.title);
  set('poc-company', poc.company);
  set('poc-email', poc.email);
  set('poc-phone', poc.phone);
}

function updatePdfTitle() {
  const bName = state.brochure?.company_name || 'Your company';
  const tName = state.target?._meta?.company_name || val(state.target?.company_profile?.name) || 'Target';
  const title = document.getElementById('pdf-title');
  const sub = document.getElementById('pdf-subtitle');
  if (title && state.brochure && state.target) title.textContent = `${bName} → ${tName}`;
  if (sub && state.brochure && state.target) sub.textContent = 'Pitch, intel, and outreach draft ready to export.';
}

async function generatePitch() {
  if (!state.brochure) return alert('Complete Exhibit A first');
  if (!state.target) return alert('Complete Exhibit B first');
  const loading = document.getElementById('pitch-loading');
  if (loading) loading.classList.add('show');
  try {
    const r = await fetch(`${API}/api/generate-pitch`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ brochure: state.brochure, target: state.target }),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || 'Pitch failed');
    state.pitch = d;
    renderPitch(d);
  } catch (e) {
    alert('Pitch failed: ' + e.message);
  } finally {
    if (loading) loading.classList.remove('show');
  }
}

function renderPitch(pitch) {
  document.getElementById('pitch-content').style.display = 'block';
  document.getElementById('match-pct').textContent = `${pitch.match_score || 0}%`;
  document.getElementById('compare-body').innerHTML = (pitch.matches || []).map(m =>
    `<tr><td>${esc(m.pitcher_offers)}</td><td>${esc(m.target_needs)}</td><td>${esc(m.fit)}</td></tr>`
  ).join('');
  const email = pitch.email_draft || {};
  document.getElementById('email-to').textContent = `${email.to_name || ''} <${email.to_email || ''}>`;
  document.getElementById('email-from').textContent = `${email.from_name || ''} <${email.from_email || ''}>`;
  document.getElementById('email-subject').textContent = email.subject || '—';
  document.getElementById('email-body').innerHTML = email.body_html || email.body || '—';
  syncOutreach();
}

function syncOutreach() {
  const basePoc = state.target ? bestPoc(state.target) : null;

  if (state.pitch) {
    const email = state.pitch.email_draft || {};
    document.getElementById('outreach-to').textContent = `${email.to_name || ''} <${email.to_email || ''}>`;
    document.getElementById('outreach-subject').textContent = email.subject || '—';
    document.getElementById('outreach-body').innerHTML = email.body_html || email.body || '—';

    syncPocCard({
      name: email.to_name || basePoc?.name || '',
      title: basePoc?.title || '',
      email: email.to_email || basePoc?.email || '',
      phone: basePoc?.phone || '',
      company: basePoc?.company || val(state.target?.company_profile?.name) || '—',
    });
  } else if (basePoc) {
    syncPocCard(basePoc);
    document.getElementById('outreach-to').textContent = basePoc.email
      ? `${basePoc.name || ''} <${basePoc.email}>`
      : 'Generate pitch in Exhibit C first';
    document.getElementById('outreach-subject').textContent = '—';
    document.getElementById('outreach-body').textContent = 'Generate pitch in Exhibit C first.';
  }
}

function sendEmail() {
  if (!state.pitch) return alert('Generate pitch in Exhibit C first');
  const email = state.pitch.email_draft || {};
  const poc = state.target ? bestPoc(state.target) : {};
  const company = poc.company || val(state.target?.company_profile?.name) || '—';
  const contact = email.to_name || poc.name || '—';
  const row = document.getElementById('outreach-log');
  if (row) {
    const now = new Date().toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    if (row.querySelector('td[colspan]')) row.innerHTML = '';
    row.insertAdjacentHTML('afterbegin',
      `<tr><td>${esc(company)}</td><td>${esc(contact)}</td><td>${now}</td><td><span class="status-pill">Sent</span></td></tr>`
    );
  }
  alert('Email logged (demo — no mail server configured).');
}

async function runAeoGeo() {
  const url = (document.getElementById('aeo-url-input')?.value || '').trim();
  if (!url) return alert('Enter a website URL e.g. https://www.buffer.com');

  const kwRaw = (document.getElementById('aeo-keywords-input')?.value || '').trim();
  const keywords = kwRaw
    ? kwRaw.split(',').map(s => s.trim()).filter(Boolean)
    : null;

  const btn = document.getElementById('aeo-run-btn');
  const loading = document.getElementById('aeo-loading');
  const empty = document.getElementById('aeo-empty');
  const content = document.getElementById('aeo-content');

  if (btn) btn.disabled = true;
  if (loading) loading.classList.add('show');
  if (empty) empty.style.display = 'none';
  if (content) content.style.display = 'none';

  try {
    const r = await fetch(`${API}/api/aeo-geo-audit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        url,
        keywords,
        use_serpapi: false,
        max_topics: keywords ? Math.min(keywords.length, 3) : 3,
      }),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || 'AEO/GEO audit failed');
    state.aeo = d;
    renderAeoGeo(d);
    if (content) content.style.display = 'block';
  } catch (e) {
    alert('AEO/GEO audit failed: ' + (e.message || e));
    if (empty) {
      empty.style.display = 'block';
      empty.textContent = 'Audit failed — check backend on :8765 and try again.';
    }
  } finally {
    if (btn) btn.disabled = false;
    if (loading) loading.classList.remove('show');
  }
}

function renderAeoGeo(data) {
  const analysis = data.analysis || {};
  const onPage = data.on_page || {};
  const signals = onPage.signals || {};
  const geo = data.geo_snapshot || {};
  const meta = data._meta || {};

  document.getElementById('aeo-hero-name').textContent = data.company_name || data.domain || '—';
  document.getElementById('aeo-hero-sub').textContent =
    `${data.domain || ''} · ${meta.search_engine || 'duckduckgo'} · ${meta.elapsed_seconds || '?'}s`;
  document.getElementById('aeo-hero-summary').textContent = analysis.visibility_summary || '';

  const kpis = [
    ['AEO score', analysis.aeo_score ?? '—'],
    ['GEO score', analysis.geo_score_blended ?? analysis.geo_score ?? '—'],
    ['Topics', (data.topics || []).length],
    ['Mentions', geo.mention_count ?? 0],
    ['Fixes', (analysis.recommendations || []).length],
  ];
  document.getElementById('aeo-kpis').innerHTML = kpis.map(([l, v]) =>
    `<div class="kpi-chip"><div class="lbl">${esc(l)}</div><div class="val">${esc(String(v))}</div></div>`
  ).join('');

  const signalTags = [
    ['H1', signals.has_h1 ? 'Yes' : 'No'],
    ['Meta', signals.has_meta_description ? 'Yes' : 'No'],
    ['About', signals.has_about_page ? 'Yes' : 'No'],
    ['FAQs', signals.faq_count ?? 0],
    ['FAQ schema', signals.has_faq_schema ? 'Yes' : 'No'],
    ['Org schema', signals.has_organization_schema ? 'Yes' : 'No'],
  ].map(([l, v]) => `<span class="tag">${esc(l)}: ${esc(String(v))}</span>`).join('');
  document.getElementById('aeo-signals').innerHTML = signalTags || '—';

  const topicsHtml = (data.topic_research || []).map(tr => {
    const winners = (tr.winner_domains || []).map(d => `<span class="tag amber">${esc(d)}</span>`).join('') || '<span class="tag">—</span>';
    const results = (tr.top_results || []).slice(0, 3).map(r =>
      `<div class="intel-row"><a href="${esc(ensureUrl(r.url))}" target="_blank" rel="noopener">${esc(r.title || r.url)}</a></div>`
    ).join('');
    return `<div class="competitor-card" style="margin-bottom:12px;">
      <strong>${esc(tr.topic)}</strong>
      <div style="margin:8px 0;">${winners}</div>
      ${results}
    </div>`;
  }).join('') || '<p class="field-value" style="color:var(--text-muted);">No topic results</p>';
  document.getElementById('aeo-topics').innerHTML = topicsHtml;

  const gapsHtml = (analysis.gaps || []).map(g =>
    `<div class="analysis-box" style="margin-bottom:10px;">
      <span class="tag red">${esc(g.severity || '')}</span>
      <span class="tag">${esc(g.area || '')}</span>
      <p style="margin-top:8px;"><strong>${esc(g.finding || '')}</strong></p>
      <p class="field-value" style="color:var(--text-muted);">${esc(g.why_it_matters || '')}</p>
    </div>`
  ).join('') || '<p class="field-value">No gaps listed</p>';
  document.getElementById('aeo-gaps').innerHTML = gapsHtml;

  const recsHtml = (analysis.recommendations || []).map(rec =>
    `<div class="competitor-card" style="margin-bottom:14px;">
      <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px;">
        <span class="tag red">${esc(rec.priority || '')}</span>
        <span class="tag">${esc(rec.type || '')}</span>
        <span class="tag amber">${esc(rec.page || '')}</span>
      </div>
      <strong>${esc(rec.title || '')}</strong>
      <p class="field-value" style="margin:8px 0;color:var(--text-muted);">${esc(rec.why || '')}</p>
      <div class="compare-table-wrap" style="overflow:auto;">
        <table class="compare-table">
          <tr><th style="width:90px;">Before</th><td><pre style="white-space:pre-wrap;margin:0;font-family:var(--font-mono);font-size:12px;">${esc(rec.before || '')}</pre></td></tr>
          <tr><th>After</th><td><pre style="white-space:pre-wrap;margin:0;font-family:var(--font-mono);font-size:12px;">${esc(rec.after || '')}</pre></td></tr>
        </table>
      </div>
    </div>`
  ).join('') || '<p class="field-value">No recommendations</p>';
  document.getElementById('aeo-recs').innerHTML = recsHtml;

  const faqsHtml = (analysis.suggested_faqs || []).map(f =>
    `<div class="intel-row" style="margin-bottom:10px;">
      <strong>Q: ${esc(f.question || '')}</strong><br>
      <span class="field-value">A: ${esc(f.answer || '')}</span>
    </div>`
  ).join('') || '<p class="field-value">No FAQs suggested</p>';
  document.getElementById('aeo-faqs').innerHTML = faqsHtml;

  const mentions = (geo.external_mentions || []).slice(0, 8).map(m =>
    `<div class="intel-row">
      <span class="tag">${esc(m.kind || 'other')}</span>
      <a href="${esc(ensureUrl(m.url))}" target="_blank" rel="noopener">${esc(m.title || m.url)}</a>
    </div>`
  ).join('');
  document.getElementById('aeo-geo').innerHTML =
    `<p class="field-value" style="margin-bottom:10px;">${esc(geo.note || '')}</p>
     <div style="margin-bottom:10px;">${(geo.mention_kinds || []).map(k => `<span class="tag amber">${esc(k)}</span>`).join('')}</div>
     ${mentions || '<p class="field-value">No external mentions found yet</p>'}`;

  document.getElementById('aeo-checklist').innerHTML =
    (analysis.distribution_checklist || []).map(c =>
      `<div class="intel-row"><span class="tag">${esc(c.helps || '')}</span> <strong>${esc(c.action || '')}</strong>
        <span style="color:var(--text-muted);"> — ${esc(c.done_hint || '')}</span></div>`
    ).join('') || '<p class="field-value">—</p>';
}

async function downloadPdf() {
  if (!state.brochure || !state.target) return alert('Complete Exhibits A & B first');
  try {
    const r = await fetch(`${API}/api/export-pdf`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ brochure: state.brochure, target: state.target, pitch: state.pitch }),
    });
    if (!r.ok) throw new Error('PDF export failed');
    const blob = new Blob([await r.arrayBuffer()], { type: 'application/pdf' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'casefile-report.pdf';
    a.click();
  } catch (e) {
    alert('PDF failed: ' + e.message);
  }
}

window.searchBrochure = searchBrochure;
window.researchTarget = researchTarget;
window.generatePitch = generatePitch;
window.downloadPdf = downloadPdf;
window.sendEmail = sendEmail;
window.syncOutreach = syncOutreach;
window.showView = showView;
window.showIntelTab = showIntelTab;
window.toggleVerbatim = toggleVerbatim;
window.runAeoGeo = runAeoGeo;

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('brochure-search-btn')?.addEventListener('click', searchBrochure);
  document.getElementById('brochure-search-input')?.addEventListener('keydown', e => {
    if (e.key === 'Enter') searchBrochure();
  });
  document.getElementById('brochure-file')?.addEventListener('change', e => {
    if (e.target.files[0]) uploadBrochure(e.target.files[0]);
  });
  document.getElementById('target-search-btn')?.addEventListener('click', researchTarget);
  document.getElementById('target-url-input')?.addEventListener('keydown', e => {
    if (e.key === 'Enter') researchTarget();
  });
  document.getElementById('pitch-btn')?.addEventListener('click', generatePitch);
  document.getElementById('pdf-btn')?.addEventListener('click', downloadPdf);
  document.getElementById('aeo-run-btn')?.addEventListener('click', runAeoGeo);
  document.getElementById('aeo-url-input')?.addEventListener('keydown', e => {
    if (e.key === 'Enter') runAeoGeo();
  });
});
