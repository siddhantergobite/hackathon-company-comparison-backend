export default function PageHeader({ exhibit, eyebrow, title, description, actions }) {
  return (
    <header className="page-header">
      <div>
        <div className="page-header__eyebrow">
          {exhibit && <span>Exhibit {exhibit}</span>}
          {exhibit && eyebrow && <span aria-hidden="true">·</span>}
          {eyebrow && <span>{eyebrow}</span>}
        </div>
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {actions && <div className="page-header__actions">{actions}</div>}
    </header>
  );
}
