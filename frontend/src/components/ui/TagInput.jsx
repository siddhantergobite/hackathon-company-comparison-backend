import { useId, useState } from 'react';
import { X } from 'lucide-react';

// Type a value and press Enter or comma to add it; Backspace on an empty input removes the last one.
export default function TagInput({ id, value, onChange, placeholder, suggestions = [], label }) {
  const [text, setText] = useState('');
  const listId = useId();

  const add = (raw) => {
    const t = raw.trim();
    if (!t) return;
    if (!value.some((v) => v.toLowerCase() === t.toLowerCase())) onChange([...value, t]);
    setText('');
  };

  return (
    <div className="tag-input">
      {value.map((t) => (
        <span className="tag" key={t}>
          {t}
          <button type="button" className="tag-input__remove" onClick={() => onChange(value.filter((v) => v !== t))} aria-label={`Remove ${t}`}>
            <X size={12} />
          </button>
        </span>
      ))}
      <input
        id={id}
        className="tag-input__field"
        value={text}
        list={suggestions.length ? listId : undefined}
        placeholder={value.length ? '' : placeholder}
        aria-label={label}
        onChange={(e) => {
          const v = e.target.value;
          if (v.endsWith(',')) add(v.slice(0, -1));
          else setText(v);
        }}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault();
            add(text);
          } else if (e.key === 'Backspace' && !text && value.length) {
            onChange(value.slice(0, -1));
          }
        }}
        onBlur={() => add(text)}
      />
      {suggestions.length > 0 && (
        <datalist id={listId}>
          {suggestions.map((s) => (
            <option key={s} value={s} />
          ))}
        </datalist>
      )}
    </div>
  );
}
