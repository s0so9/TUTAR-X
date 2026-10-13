import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { App } from '@capacitor/app';
import { Capacitor } from '@capacitor/core';
import { consumeAndroidBackOverlay } from './androidBack';

/**
 * Maps the Android system back button to in-app navigation.
 */
export function AndroidBackHandler() {
  const navigate = useNavigate();

  useEffect(() => {
    if (!Capacitor.isNativePlatform()) {
      return;
    }

    const listenerPromise = App.addListener('backButton', () => {
      if (consumeAndroidBackOverlay()) {
        return;
      }

      const historyIndex = window.history.state?.idx;
      if (typeof historyIndex === 'number' && historyIndex > 0) {
        navigate(-1);
        return;
      }

      App.exitApp();
    });

    return () => {
      void listenerPromise.then((handle) => handle.remove());
    };
  }, [navigate]);

  return null;
}
