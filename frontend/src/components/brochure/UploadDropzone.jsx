import { useRef, useState } from 'react';
import { UploadCloud } from 'lucide-react';
import Button from '../ui/Button';
import { useToast } from '../../context/ToastContext';

const ACCEPT = '.pdf,.docx,.doc,.png,.jpg,.jpeg,.webp';
const ALLOWED = ACCEPT.split(',');
const MAX_BYTES = 25 * 1024 * 1024;

export default function UploadDropzone({ onFile, disabled }) {
  const inputRef = useRef(null);
  const [over, setOver] = useState(false);
  const toast = useToast();

  const accept = (file) => {
    if (!file) return;
    const ext = '.' + file.name.split('.').pop().toLowerCase();
    if (!ALLOWED.includes(ext)) {
      toast.error('Unsupported file type. Use PDF, DOCX, DOC, PNG, JPG or WEBP.');
      return;
    }
    if (file.size > MAX_BYTES) {
      toast.error('File exceeds the 25MB limit.');
      return;
    }
    onFile(file);
  };

  return (
    <div
      className={`dropzone ${over ? 'is-over' : ''}`}
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        if (!disabled) accept(e.dataTransfer.files?.[0]);
      }}
    >
      <div className="dropzone__icon">
        <UploadCloud size={26} aria-hidden="true" />
      </div>
      <h3>Upload brochure</h3>
      <p>Drag &amp; drop, or browse — PDF, DOCX or image, up to 25MB</p>
      <input
        ref={inputRef}
        type="file"
        className="sr-only"
        accept={ACCEPT}
        tabIndex={-1}
        aria-hidden="true"
        onChange={(e) => {
          accept(e.target.files?.[0]);
          e.target.value = '';
        }}
      />
      <Button disabled={disabled} onClick={() => inputRef.current?.click()}>
        Choose file
      </Button>
    </div>
  );
}
