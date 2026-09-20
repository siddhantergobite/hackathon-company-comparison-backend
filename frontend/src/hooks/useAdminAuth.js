import { useCallback, useEffect, useState } from 'react';
import { adminApi, adminKey, apiErrorMessage } from '../api/events';

// The admin key lives in sessionStorage only (cleared when the tab closes).
export function useAdminAuth(verify = adminApi.verify) {
  const [authed, setAuthed] = useState(() => Boolean(adminKey.get()));
  const [error, setError] = useState('');
  const [checking, setChecking] = useState(false);

  useEffect(() => {
    const lost = () => {
      setAuthed(false);
      setError('Your admin session is no longer valid. Please sign in again.');
    };
    window.addEventListener('eventhub:auth-lost', lost);
    return () => window.removeEventListener('eventhub:auth-lost', lost);
  }, []);

  const login = useCallback(async (key) => {
    setChecking(true);
    setError('');
    try {
      await verify(key.trim());
      adminKey.set(key.trim());
      setAuthed(true);
    } catch (err) {
      setError(err.response?.status === 401 ? 'That admin key is not valid.' : apiErrorMessage(err));
    } finally {
      setChecking(false);
    }
  }, []);

  const logout = useCallback(() => {
    adminKey.clear();
    setAuthed(false);
    setError('');
  }, []);

  return { authed, login, logout, error, checking };
}
