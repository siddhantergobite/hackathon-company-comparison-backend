import { useEffect, useState } from 'react';
import { CalendarDays } from 'lucide-react';

const hash = (s) => [...String(s || '')].reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 7);

// Falls back to a deterministic gradient when there is no image or it fails to load.
export default function EventImage({ src, title, className = '', iconSize = 34 }) {
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [src]);

  if (!src || failed) {
    return (
      <div className={`ev-img ev-img--fallback ${className}`} style={{ '--hue': hash(title) % 360 }} aria-hidden="true">
        <CalendarDays size={iconSize} />
      </div>
    );
  }
  return <img className={`ev-img ${className}`} src={src} alt="" loading="lazy" onError={() => setFailed(true)} referrerPolicy="no-referrer" />;
}
