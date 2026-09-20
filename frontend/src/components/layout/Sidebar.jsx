import { NavLink } from 'react-router-dom';
import { Check, FileSearch } from 'lucide-react';
import { useCasefile } from '../../context/CasefileContext';
import { EVENT_HUB, NEWS_HUB, TOOLS, WORKFLOW } from '../../config/navigation';

function NavItem({ item, state, onNavigate }) {
  const Icon = item.icon;
  const done = item.isDone(state);
  return (
    <li>
      <NavLink
        to={item.path}
        onClick={onNavigate}
        className={({ isActive }) => `nav-link ${isActive ? 'is-active' : ''}`}
      >
        <span className="nav-link__icon">
          <Icon size={18} aria-hidden="true" />
        </span>
        <span className="nav-link__text">
          <span className="nav-link__title">{item.title}</span>
          <span className="nav-link__hint">
            {item.exhibit ? `Exhibit ${item.exhibit} · ${item.hint}` : item.hint}
          </span>
        </span>
        {done && <Check size={16} className="nav-link__done" aria-label="Completed" />}
      </NavLink>
    </li>
  );
}

export default function Sidebar({ open, onNavigate }) {
  const state = useCasefile();
  return (
    <aside className={`sidebar ${open ? 'is-open' : ''}`} aria-label="Primary">
      <NavLink to="/brochure" className="brand" onClick={onNavigate}>
        <span className="brand__mark">
          <FileSearch size={20} aria-hidden="true" />
        </span>
        <span>
          <span className="brand__name" style={{ display: 'block' }}>
            Casefile
          </span>
          <span className="brand__tag" style={{ display: 'block' }}>
            Client intelligence &amp; outreach
          </span>
        </span>
      </NavLink>

      <nav>
        <div className="nav-group">
          <div className="nav-group__label">Workflow</div>
          <ul className="nav-list">
            {WORKFLOW.map((item) => (
              <NavItem key={item.path} item={item} state={state} onNavigate={onNavigate} />
            ))}
          </ul>
        </div>
        <div className="nav-group">
          <div className="nav-group__label">Tools</div>
          <ul className="nav-list">
            {TOOLS.map((item) => (
              <NavItem key={item.path} item={item} state={state} onNavigate={onNavigate} />
            ))}
          </ul>
        </div>
        <div className="nav-group">
          <div className="nav-group__label">Event Hub</div>
          <ul className="nav-list">
            {EVENT_HUB.map((item) => (
              <NavItem key={item.path} item={item} state={state} onNavigate={onNavigate} />
            ))}
          </ul>
        </div>
        <div className="nav-group">
          <div className="nav-group__label">News</div>
          <ul className="nav-list">
            {NEWS_HUB.map((item) => (
              <NavItem key={item.path} item={item} state={state} onNavigate={onNavigate} />
            ))}
          </ul>
        </div>
      </nav>

      <div className="sidebar__footer">Public sources only — unverified facts are left blank, never guessed.</div>
    </aside>
  );
}
