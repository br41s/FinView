import { useCallback, useEffect, useState } from "react";

const STORAGE_KEY = "fv-privacy";

// Blurs sensitive monetary values app-wide. Persisted in localStorage so the
// choice survives reloads and stays in sync across pages. Starts false to
// avoid a flash of blur before the stored value loads.
export function usePrivacyToggle() {
  const [privacy, setPrivacy] = useState(false);

  useEffect(() => {
    setPrivacy(localStorage.getItem(STORAGE_KEY) === "1");
  }, []);

  const togglePrivacy = useCallback(() => {
    setPrivacy((prev) => {
      const next = !prev;
      localStorage.setItem(STORAGE_KEY, next ? "1" : "0");
      return next;
    });
  }, []);

  return { privacy, togglePrivacy };
}
