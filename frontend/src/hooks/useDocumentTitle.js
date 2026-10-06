import { useEffect } from 'react';

export function useDocumentTitle(title) {
  useEffect(() => {
    const previous = document.title;
    if (title) document.title = `${title} · CompareFlow.ai`;
    return () => {
      document.title = previous;
    };
  }, [title]);
}
