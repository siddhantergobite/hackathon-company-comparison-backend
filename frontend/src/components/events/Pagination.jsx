import { ChevronLeft, ChevronRight } from 'lucide-react';

function pagesToShow(page, total) {
  const set = new Set([1, total, page - 1, page, page + 1]);
  const nums = [...set].filter((n) => n >= 1 && n <= total).sort((a, b) => a - b);
  const out = [];
  nums.forEach((n, i) => {
    if (i && n - nums[i - 1] > 1) out.push('gap-' + n);
    out.push(n);
  });
  return out;
}

export default function Pagination({ page, totalPages, onChange, disabled = false }) {
  if (totalPages <= 1) return null;
  return (
    <nav className="ev-pagination" aria-label="Pagination">
      <button type="button" className="btn btn--secondary btn--sm" disabled={disabled || page <= 1} onClick={() => onChange(page - 1)}>
        <ChevronLeft size={16} aria-hidden="true" /> Previous
      </button>
      <ul className="ev-pagination__pages">
        {pagesToShow(page, totalPages).map((p) =>
          typeof p === 'string' ? (
            <li key={p} aria-hidden="true" className="ev-pagination__gap">
              …
            </li>
          ) : (
            <li key={p}>
              <button
                type="button"
                className={`ev-pagination__page ${p === page ? 'is-current' : ''}`}
                aria-current={p === page ? 'page' : undefined}
                aria-label={`Page ${p}`}
                disabled={disabled}
                onClick={() => onChange(p)}
              >
                {p}
              </button>
            </li>
          ),
        )}
      </ul>
      <button type="button" className="btn btn--secondary btn--sm" disabled={disabled || page >= totalPages} onClick={() => onChange(page + 1)}>
        Next <ChevronRight size={16} aria-hidden="true" />
      </button>
    </nav>
  );
}
