import DOMPurify from 'dompurify';

// Email drafts are LLM output built from scraped web content, so never inject them unsanitised.
DOMPurify.addHook('afterSanitizeAttributes', (node) => {
  if (node.tagName === 'A') {
    node.setAttribute('target', '_blank');
    node.setAttribute('rel', 'noopener noreferrer');
  }
});

export function sanitizeHtml(html) {
  return DOMPurify.sanitize(String(html || ''), { USE_PROFILES: { html: true } });
}

export function htmlToText(html) {
  const doc = new DOMParser().parseFromString(sanitizeHtml(html), 'text/html');
  doc.querySelectorAll('br').forEach((br) => br.replaceWith('\n'));
  doc.querySelectorAll('p, div, li').forEach((el) => el.append('\n'));
  return (doc.body.textContent || '').replace(/\n{3,}/g, '\n\n').trim();
}
