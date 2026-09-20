import { useEffect } from 'react';

export function useDocumentTitle(title) {
  useEffect(() => {
    const previous = document.title;
    if (title) document.title = `${title} · Casefile`;
    return () => {
      document.title = previous;
    };
  }, [title]);
}
