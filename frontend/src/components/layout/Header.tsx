import { useEffect, useState } from 'react';
import { Menu } from 'lucide-react';
import { GlobalSearch } from '../search/GlobalSearch';
import './Header.css';

interface HeaderProps {
  onToggleMobileMenu: () => void;
}

const dateFormatter = new Intl.DateTimeFormat('tr-TR', {
  weekday: 'long',
  day: 'numeric',
  month: 'long',
});

const timeFormatter = new Intl.DateTimeFormat('tr-TR', {
  hour: '2-digit',
  minute: '2-digit',
});

/** Local date and time, refreshed every 30 seconds (kickoffs are read against it). */
function useNow(intervalMs = 30_000): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), intervalMs);
    return () => window.clearInterval(id);
  }, [intervalMs]);
  return now;
}

export function Header({ onToggleMobileMenu }: HeaderProps) {
  const [searchOpen, setSearchOpen] = useState(false);
  const now = useNow();

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
      e.preventDefault();
      setSearchOpen(true);
    }
  };

  return (
    <header className="app-header" onKeyDown={handleKeyDown}>
      <button className="mobile-menu-button" onClick={onToggleMobileMenu} aria-label="Menüyü aç">
        <Menu size={20} strokeWidth={1.5} aria-hidden="true" />
      </button>

      <div className="header-search">
        <GlobalSearch isOpen={searchOpen} onOpenChange={setSearchOpen} />
      </div>

      <time className="header-clock" dateTime={now.toISOString()}>
        <span className="header-clock__date">{dateFormatter.format(now)}</span>
        <span className="header-clock__time numeral">{timeFormatter.format(now)}</span>
      </time>
    </header>
  );
}
