/**
 * Android back-button handlers.
 * Overlay handlers run first; returning true consumes the event.
 */

type BackHandler = () => boolean;

const overlayHandlers: BackHandler[] = [];

export function registerAndroidBackHandler(handler: BackHandler): () => void {
  overlayHandlers.unshift(handler);
  return () => {
    const index = overlayHandlers.indexOf(handler);
    if (index >= 0) {
      overlayHandlers.splice(index, 1);
    }
  };
}

export function consumeAndroidBackOverlay(): boolean {
  return overlayHandlers.some((handler) => handler());
}
