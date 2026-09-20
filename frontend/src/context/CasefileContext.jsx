import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../api/client';
import { useToast } from './ToastContext';
import { getTargetName } from '../utils/target';

const CasefileContext = createContext(null);

const STORAGE_KEY = 'casefile:session:v1';
const EMPTY = { brochure: null, target: null, pitch: null, aeo: null, outreachLog: [] };

function loadSession() {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? { ...EMPTY, ...JSON.parse(raw) } : EMPTY;
  } catch {
    return EMPTY;
  }
}

function saveSession(data) {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(data));
  } catch {
    /* quota exceeded or storage blocked — the session simply isn't restored on reload */
  }
}

// Owns the casefile data and every API call, so long-running requests
// (research can take minutes) keep going while the user moves between pages.
export function CasefileProvider({ children }) {
  const toast = useToast();
  const [data, setData] = useState(loadSession);
  const [requests, setRequests] = useState({});
  const dataRef = useRef(data);
  const inFlight = useRef(new Set());

  useEffect(() => {
    dataRef.current = data;
    saveSession(data);
  }, [data]);

  const setSlice = useCallback((key, value) => setData((d) => ({ ...d, [key]: value })), []);

  const track = useCallback(
    async (key, work) => {
      if (inFlight.current.has(key)) return false;
      inFlight.current.add(key);
      setRequests((r) => ({ ...r, [key]: { loading: true, error: null } }));
      try {
        await work();
        setRequests((r) => ({ ...r, [key]: { loading: false, error: null } }));
        return true;
      } catch (e) {
        const message = e?.message || 'Something went wrong';
        setRequests((r) => ({ ...r, [key]: { loading: false, error: message } }));
        toast.error(message);
        return false;
      } finally {
        inFlight.current.delete(key);
      }
    },
    [toast],
  );

  const actions = useMemo(
    () => ({
      searchBrochure: (query) =>
        track('brochure', async () => setSlice('brochure', await api.brochureSearch(query))),

      uploadBrochure: (file) =>
        track('brochure', async () => setSlice('brochure', await api.brochureUpload(file))),

      researchTarget: (url) =>
        track('target', async () => setSlice('target', await api.companyResearch(url))),

      generatePitch: () =>
        track('pitch', async () => {
          const { brochure, target } = dataRef.current;
          setSlice('pitch', await api.generatePitch(brochure, target));
        }),

      runAeoAudit: (url, keywords) =>
        track('aeo', async () => setSlice('aeo', await api.aeoGeoAudit(url, keywords))),

      downloadPdf: () =>
        track('pdf', async () => {
          const { brochure, target, pitch, aeo } = dataRef.current;
          const { blob, filename } = await api.exportPdf({ brochure, target, pitch, aeo });
          const slug = String(getTargetName(target)).toLowerCase().replace(/[^a-z0-9]+/g, '-');
          const link = document.createElement('a');
          link.href = URL.createObjectURL(blob);
          link.download = filename || `casefile-${slug}.pdf`;
          link.click();
          URL.revokeObjectURL(link.href);
          toast.success('Casefile PDF downloaded.');
        }),

      logOutreach: (entry) =>
        setData((d) => ({ ...d, outreachLog: [entry, ...d.outreachLog] })),

      resetCasefile: () => setData(EMPTY),
    }),
    [track, setSlice, toast],
  );

  const value = useMemo(() => ({ ...data, requests, ...actions }), [data, requests, actions]);
  return <CasefileContext.Provider value={value}>{children}</CasefileContext.Provider>;
}

export function useCasefile() {
  const ctx = useContext(CasefileContext);
  if (!ctx) throw new Error('useCasefile must be used inside <CasefileProvider>');
  return ctx;
}
