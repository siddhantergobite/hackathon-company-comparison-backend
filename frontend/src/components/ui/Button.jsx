import { Link } from 'react-router-dom';
import { Loader2 } from 'lucide-react';

function classesFor(variant, size, className) {
  return ['btn', `btn--${variant}`, size ? `btn--${size}` : '', className].filter(Boolean).join(' ');
}

export default function Button({
  variant = 'primary',
  size,
  loading = false,
  icon: Icon,
  className = '',
  children,
  disabled,
  type = 'button',
  ...rest
}) {
  return (
    <button
      type={type}
      className={classesFor(variant, size, className)}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading ? <Loader2 size={16} className="spin" aria-hidden="true" /> : Icon && <Icon size={16} aria-hidden="true" />}
      {children}
    </button>
  );
}

// A router link styled as a button (an <a>, never a <button> nested in a link).
export function LinkButton({ to, variant = 'primary', size, icon: Icon, className = '', children, ...rest }) {
  return (
    <Link to={to} className={classesFor(variant, size, className)} {...rest}>
      {Icon && <Icon size={16} aria-hidden="true" />}
      {children}
    </Link>
  );
}
