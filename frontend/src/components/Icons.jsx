/* Small inline SVG icon set — no icon dependency, works offline. */

export function Logo({ size = 28 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" fill="none" aria-hidden="true">
      <circle cx="24" cy="24" r="22" fill="currentColor" opacity="0.12" />
      <path
        d="M8 32c4-1 6-6 10-6s5 4 9 4 6-8 13-9"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
      />
      <circle cx="34" cy="14" r="5" fill="currentColor" />
      <path
        d="M14 38c3-2 7-2 10 0"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
        opacity="0.55"
      />
    </svg>
  )
}

const paths = {
  explore_nature: (
    <>
      <path d="M12 27 18 15l4 7 3-4 5 9z" />
      <circle cx="24" cy="9" r="3" />
      <path d="M6 32h32" />
    </>
  ),
  move: (
    <>
      <path d="M14 8c-2 4-2 8 1 12s4 6 3 10" />
      <path d="M27 12c-2 4-1 7 2 10s3 6 2 9" />
      <circle cx="14" cy="6" r="2.4" />
      <circle cx="27" cy="10" r="2.4" />
    </>
  ),
  clear_my_head: (
    <>
      <path d="M8 20c4-6 10-9 16-9s12 3 16 9" />
      <path d="M12 26c3 4 7 6 12 6s9-2 12-6" />
      <path d="M18 22h8" />
    </>
  ),
  observe: (
    <>
      <path d="M4 24s7-11 20-11 20 11 20 11-7 11-20 11S4 24 4 24z" />
      <circle cx="24" cy="24" r="5.5" />
    </>
  ),
}

export function ActivityIcon({ name, size = 30 }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 48 48"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name] || paths.explore_nature}
    </svg>
  )
}

export function CheckIcon({ size = 18 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="m5 12.5 4.5 4.5L19 7.5"
        stroke="currentColor"
        strokeWidth="2.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export function SkipIcon({ size = 18 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M6 6v12M18 6v12M8 12l8-6M8 12l8 6"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export function ClockIcon({ size = 18 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="8.5" stroke="currentColor" strokeWidth="2.2" />
      <path d="M12 7.5V12l3 2" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
    </svg>
  )
}

export function PauseIcon({ size = 18 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <rect x="7" y="5.5" width="3.6" height="13" rx="1.2" />
      <rect x="13.4" y="5.5" width="3.6" height="13" rx="1.2" />
    </svg>
  )
}

export function PlayIcon({ size = 18 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M8 5.5v13l11-6.5z" />
    </svg>
  )
}

export function FlagIcon({ size = 18 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M6 21V4.5m0 0h11l-2.2 3.6L17 12H6"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}
