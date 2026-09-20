import { useState } from 'react';
import { FileSearch, Search } from 'lucide-react';
import { useCasefile } from '../context/CasefileContext';
import { useToast } from '../context/ToastContext';
import { Banner, Card, CardHeader, EmptyState, LoadingPanel, PageHeader, SearchBar } from '../components/ui';
import UploadDropzone from '../components/brochure/UploadDropzone';
import BrochureProfile from '../components/brochure/BrochureProfile';

export default function BrochurePage() {
  const { brochure, requests, searchBrochure, uploadBrochure } = useCasefile();
  const toast = useToast();
  const [query, setQuery] = useState('');
  const { loading, error } = requests.brochure || {};

  const onSearch = () => {
    const q = query.trim();
    if (!q) {
      toast.error('Enter a company name or URL, e.g. https://ergobite.com/us/');
      return;
    }
    searchBrochure(q);
  };

  return (
    <>
      <PageHeader
        exhibit="A"
        eyebrow="Your company"
        title="Brochure intake & extraction"
        description="Upload a brochure, or search a company name to pull one automatically. The model reads it in full and stores every field for reuse in the rest of the casefile."
      />

      <div className="grid-2">
        <div className="stack">
          <UploadDropzone onFile={uploadBrochure} disabled={loading} />
          <div className="divider">or search instead</div>
          <Card>
            <CardHeader icon={Search} title="Search a company" />
            <SearchBar
              value={query}
              onChange={setQuery}
              onSubmit={onSearch}
              placeholder="Company name or URL, e.g. Ergobite"
              buttonLabel="Search"
              inputIcon={Search}
              loading={loading}
            />
            <p className="form-hint">We read the company's public website and build the same profile as a brochure upload.</p>
          </Card>
        </div>

        <div className="stack">
          {loading ? (
            <LoadingPanel
              title="Extracting brochure with AI…"
              steps={['Reading the source', 'Extracting services and industries', 'Structuring the company profile']}
            />
          ) : (
            <>
              {error && (
                <Banner tone="error" title="Couldn't read the brochure">
                  {error}
                </Banner>
              )}
              {brochure ? (
                <BrochureProfile brochure={brochure} />
              ) : (
                <EmptyState icon={FileSearch} title="No brochure yet">
                  Upload a brochure or search your company to begin. The extracted profile will appear here.
                </EmptyState>
              )}
            </>
          )}
        </div>
      </div>
    </>
  );
}
