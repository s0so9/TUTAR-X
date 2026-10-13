import { Capacitor } from '@capacitor/core';
import { StatusBar, Style } from '@capacitor/status-bar';
import { SplashScreen } from '@capacitor/splash-screen';

/**
 * Apply dark status bar / splash behavior on native Android.
 */
export async function initNativeChrome(): Promise<void> {
  if (!Capacitor.isNativePlatform()) {
    return;
  }

  try {
    await StatusBar.setStyle({ style: Style.Light });
    await StatusBar.setBackgroundColor({ color: '#0a0a0f' });
  } catch {
    // Status bar plugin may be unavailable in some WebView previews.
  }

  try {
    await SplashScreen.hide();
  } catch {
    // Splash screen plugin may already be hidden.
  }
}
