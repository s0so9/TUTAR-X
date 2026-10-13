import { useState, ReactNode, useEffect } from 'react';
import { Sidebar } from './Sidebar';
import { Header } from './Header';
import { NetworkStatusBanner } from './NetworkStatusBanner';
import { registerAndroidBackHandler } from '../../native/androidBack';
import './AppLayout.css';

interface AppLayoutProps {
  children: ReactNode;
}

export function AppLayout({ children }: AppLayoutProps) {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const toggleSidebar = () => {
    setSidebarCollapsed(!sidebarCollapsed);
  };

  const toggleMobileMenu = () => {
    setMobileMenuOpen(!mobileMenuOpen);
  };

  const closeMobileMenu = () => {
    setMobileMenuOpen(false);
  };

  useEffect(() => {
    return registerAndroidBackHandler(() => {
      if (!mobileMenuOpen) {
        return false;
      }
      setMobileMenuOpen(false);
      return true;
    });
  }, [mobileMenuOpen]);

  return (
    <div className="app-layout">
      <Sidebar
        collapsed={sidebarCollapsed}
        mobileOpen={mobileMenuOpen}
        onCollapse={toggleSidebar}
        onCloseMobile={closeMobileMenu}
      />

      <div className={`app-layout__main ${sidebarCollapsed ? 'sidebar-collapsed' : ''}`}>
        <NetworkStatusBanner />
        <Header onToggleMobileMenu={toggleMobileMenu} />

        <main className="app-layout__content">{children}</main>
      </div>

      {/* Mobile overlay */}
      {mobileMenuOpen && (
        <div
          className="app-layout__overlay"
          onClick={closeMobileMenu}
          aria-hidden="true"
        />
      )}
    </div>
  );
}
