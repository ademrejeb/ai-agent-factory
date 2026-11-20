export function Logo({ size = 32, className }: { size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      className={className}
      aria-hidden="true"
      focusable="false"
    >
      <defs>
        <linearGradient id="factory-mark" x1="4" y1="2" x2="28" y2="30" gradientUnits="userSpaceOnUse">
          <stop stopColor="#aab5ff" />
          <stop offset="0.55" stopColor="#7c8cff" />
          <stop offset="1" stopColor="#4f5fe8" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="9" fill="url(#factory-mark)" />
      <path
        d="M8.5 22.5 16 7.5l7.5 15"
        fill="none"
        stroke="#fff"
        strokeWidth="2.1"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M11.6 18.4h8.8"
        fill="none"
        stroke="#fff"
        strokeOpacity="0.78"
        strokeWidth="1.7"
        strokeLinecap="round"
      />
    </svg>
  );
}
