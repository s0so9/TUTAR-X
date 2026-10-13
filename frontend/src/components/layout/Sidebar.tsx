import { NavLink } from 'react-router-dom';
import {
  CalendarClock,
  CalendarDays,
  ChartColumn,
  CircleCheck,
  Crosshair,
  Layers,
  PanelLeftClose,
  PanelLeftOpen,
  Radio,
  Settings,
  Star,
  Target,
  Trophy,
  type LucideIcon,
  X,
} from 'lucide-react';
import './Sidebar.css';

interface SidebarProps {
  collapsed: boolean;
  mobileOpen: boolean;
  onCollapse: () => void;
  onCloseMobile: () => void;
}

interface NavItem {
  path: string;
  label: string;
  icon: LucideIcon;
}

interface NavGroup {
  label: string;
  items: NavItem[];
}

const navigationGroups: NavGroup[] = [
  {
    label: 'Maç gecesi',
    items: [
      { path: '/', label: 'Bugün', icon: Crosshair },
      { path: '/matches', label: 'Maç Merkezi', icon: CalendarDays },
      { path: '/live', label: 'Canlı', icon: Radio },
      { path: '/predictions', label: 'Tahminler', icon: Target },
    ],
  },
  {
    label: 'Fikstür',
    items: [
      { path: '/upcoming', label: 'Yaklaşan', icon: CalendarClock },
      { path: '/completed', label: 'Biten', icon: CircleCheck },
      { path: '/popular-leagues', label: 'Popüler Ligler', icon: Trophy },
      { path: '/favorites', label: 'Favoriler', icon: Star },
      { path: '/easy-matches', label: 'Kolay Maçlar', icon: Layers },
    ],
  },
  {
    label: 'Sistem',
    items: [
      { path: '/analytics', label: 'Analiz', icon: ChartColumn },
      { path: '/settings', label: 'Ayarlar', icon: Settings },
    ],
  },
];

export function Sidebar({ collapsed, mobileOpen, onCollapse, onCloseMobile }: SidebarProps) {
  const handleNavClick = () => {
    if (window.innerWidth <= 768) {
      onCloseMobile();
    }
  };

  const CollapseIcon = collapsed ? PanelLeftOpen : PanelLeftClose;

  return (
    <aside
      className={`sidebar ${collapsed ? 'sidebar--collapsed' : ''} ${
        mobileOpen ? 'sidebar--mobile-open' : ''
      }`}
      aria-label="Ana gezinme"
    >
      <NavLink to="/" className="sidebar__brand" onClick={handleNavClick} aria-label="TUTAR X — Bugün">
        <span className="sidebar__wordmark" aria-hidden="true">
          {collapsed ? (
            <>T<span className="sidebar__wordmark-x">X</span></>
          ) : (
            <>TUTAR <span className="sidebar__wordmark-x">X</span></>
          )}
        </span>
        {!collapsed && <span className="sidebar__tagline">Maçın geleceğini veriden oku.</span>}
      </NavLink>

      {mobileOpen && (
        <button
          type="button"
          className="sidebar__close-mobile"
          onClick={onCloseMobile}
          aria-label="Menüyü kapat"
        >
          <X size={18} strokeWidth={1.5} aria-hidden="true" />
        </button>
      )}

      <nav className="sidebar__nav">
        {navigationGroups.map((group) => (
          <div className="sidebar__group" key={group.label}>
            {!collapsed && <div className="sidebar__group-label apparatus">{group.label}</div>}
            <ul className="sidebar__nav-list" role="list">
              {group.items.map((item) => {
                const Icon = item.icon;
                return (
                  <li key={item.path}>
                    <NavLink
                      to={item.path}
                      className={({ isActive }) =>
                        `sidebar__nav-link ${isActive ? 'sidebar__nav-link--active' : ''}`
                      }
                      onClick={handleNavClick}
                      title={collapsed ? item.label : undefined}
                      end={item.path === '/'}
                    >
                      <Icon className="sidebar__nav-icon" size={17} strokeWidth={1.5} aria-hidden="true" />
                      {!collapsed && <span className="sidebar__nav-label">{item.label}</span>}
                    </NavLink>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      <button
        className="sidebar__collapse-btn"
        onClick={onCollapse}
        aria-label={collapsed ? 'Menüyü genişlet' : 'Menüyü daralt'}
        aria-expanded={!collapsed}
      >
        <CollapseIcon size={16} strokeWidth={1.5} aria-hidden="true" />
        {!collapsed && <span>Daralt</span>}
      </button>
    </aside>
  );
}
