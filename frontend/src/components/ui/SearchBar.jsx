import Button from './Button';

export default function SearchBar({
  value,
  onChange,
  onSubmit,
  placeholder,
  buttonLabel = 'Search',
  buttonIcon,
  inputIcon: InputIcon,
  loading = false,
  disabled = false,
  label,
  inputType = 'text',
}) {
  return (
    <form
      className="search-bar"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit();
      }}
    >
      <div className="input-wrap">
        {InputIcon && <InputIcon size={17} aria-hidden="true" />}
        <input
          className={`input ${InputIcon ? 'input--icon' : ''}`}
          type={inputType}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          aria-label={label || placeholder}
          disabled={disabled || loading}
          autoComplete="off"
          spellCheck="false"
        />
      </div>
      <Button type="submit" icon={buttonIcon} loading={loading} disabled={disabled}>
        {buttonLabel}
      </Button>
    </form>
  );
}
