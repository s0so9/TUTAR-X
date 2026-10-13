import { useCallback, useEffect, useState } from 'react';
import { Capacitor } from '@capacitor/core';
import { Network } from '@capacitor/network';
import './NetworkStatusBanner.css';

/**
 * Shows a Turkish offline warning with retry. Does not invent match data.
 */
export function NetworkStatusBanner() {
  const [offline, setOffline] = useState(false);

  const refreshStatus = useCallback(async () => {
    try {
      if (Capacitor.isPluginAvailable('Network')) {
        const status = await Network.getStatus();
        setOffline(!status.connected);
        return;
      }
    } catch {
      // Fall through to browser online flag.
    }
    setOffline(typeof navigator !== 'undefined' && navigator.onLine === false);
  }, []);

  useEffect(() => {
    void refreshStatus();

    let removeNetworkListener: (() => void) | undefined;

    if (Capacitor.isPluginAvailable('Network')) {
      const listenerPromise = Network.addListener('networkStatusChange', (status) => {
        setOffline(!status.connected);
      });
      removeNetworkListener = () => {
        void listenerPromise.then((handle) => handle.remove());
      };
    }

    const handleBrowserChange = () => {
      setOffline(navigator.onLine === false);
    };

    window.addEventListener('online', handleBrowserChange);
    window.addEventListener('offline', handleBrowserChange);

    return () => {
      removeNetworkListener?.();
      window.removeEventListener('online', handleBrowserChange);
      window.removeEventListener('offline', handleBrowserChange);
    };
  }, [refreshStatus]);

  if (!offline) {
    return null;
  }

  return (
    <div className="network-status-banner" role="alert">
      <p className="network-status-banner__text">
        İnternet bağlantısı yok. Canlı maçlar ve tahminler için bağlantı gerekli.
      </p>
      <button type="button" className="network-status-banner__retry" onClick={() => void refreshStatus()}>
        Tekrar dene
      </button>
    </div>
  );
}
