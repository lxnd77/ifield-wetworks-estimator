import { useApiBusy } from "../loading";

export function Spinner({ className = "h-4 w-4" }) {
  return (
    <svg className={`animate-spin ${className}`} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" className="opacity-20" />
      <path d="M22 12a10 10 0 0 0-10-10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

// Full-width placeholder for a page whose data hasn't arrived yet.
export function PageLoading({ label = "Loading..." }) {
  return (
    <div role="status" className="flex items-center justify-center gap-2 py-16 text-sm text-ink/50">
      <Spinner className="h-5 w-5 text-ruby" />
      {label}
    </div>
  );
}

// Thin indeterminate bar pinned to the top of the window while any API
// request is in flight (see loading.js).
export function LoadingBar() {
  const busy = useApiBusy();
  if (!busy) return null;
  return (
    <div role="progressbar" aria-label="Loading" className="fixed top-0 inset-x-0 h-0.5 z-50 overflow-hidden bg-ruby/15">
      <div className="loading-bar-slide h-full w-1/3 bg-ruby" />
    </div>
  );
}
