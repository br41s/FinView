import { useCallback, useSyncExternalStore } from "react";

const STORAGE_KEY = "fv-privacy";
const CHANGE_EVENT = "fv-privacy-change";

// localStorage as an external store. `storage` fires for writes from other
// tabs; our own writes don't fire it, hence the custom event on toggle.
function subscribe(onChange: () => void) {
  window.addEventListener(CHANGE_EVENT, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(CHANGE_EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}

function getSnapshot(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

// Server render (and hydration) is always unblurred: the stored choice is
// only readable on the client, and rendering it early would mismatch the HTML.
const getServerSnapshot = () => false;

// Blurs sensitive monetary values app-wide. Persisted in localStorage so the
// choice survives reloads and stays in sync across pages. Starts false to
// avoid a flash of blur before the stored value loads.
export function usePrivacyToggle() {
  const privacy = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  const togglePrivacy = useCallback(() => {
    localStorage.setItem(STORAGE_KEY, getSnapshot() ? "0" : "1");
    window.dispatchEvent(new Event(CHANGE_EVENT));
  }, []);

  return { privacy, togglePrivacy };
}
