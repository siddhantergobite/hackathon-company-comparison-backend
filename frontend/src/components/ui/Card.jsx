export function Card({ as: Tag = 'section', pad = true, flush = false, accent = false, className = '', children, ...rest }) {
  const classes = ['card', pad && !flush ? 'card--pad' : '', flush ? 'card--flush' : '', accent ? 'card--accent' : '', className]
    .filter(Boolean)
    .join(' ');
  return (
    <Tag className={classes} {...rest}>
      {children}
    </Tag>
  );
}

export function CardHeader({ icon: Icon, title, actions }) {
  return (
    <div className="card__head">
      <h3 className="card__title">
        {Icon && <Icon size={18} aria-hidden="true" />}
        {title}
      </h3>
      {actions}
    </div>
  );
}

export function FieldLabel({ children }) {
  return <span className="field-label">{children}</span>;
}
