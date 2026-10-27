import { useEffect, useState } from "react";

// Count of in-flight API requests, fed by the axios interceptors in api.js.
// The global LoadingBar in Layout subscribes to it, so every request shows
// progress without each page having to track it.
let pending = 0;
const listeners = new Set();

const emit = () => listeners.forEach((fn) => fn(pending));

export const requestStarted = () => { pending += 1; emit(); };
export const requestFinished = () => { pending = Math.max(0, pending - 1); emit(); };

// True while any request is in flight. `delayMs` skips the indicator for
// requests that finish faster than that, so quick saves don't flash it.
export function useApiBusy(delayMs = 150) {
  const [count, setCount] = useState(pending);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    listeners.add(setCount);
    return () => { listeners.delete(setCount); };
  }, []);

  useEffect(() => {
    if (count === 0) {
      setBusy(false);
      return undefined;
    }
    const t = setTimeout(() => setBusy(true), delayMs);
    return () => clearTimeout(t);
  }, [count > 0, delayMs]); // eslint-disable-line react-hooks/exhaustive-deps

  return busy;
}
