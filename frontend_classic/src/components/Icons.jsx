// Minimal inline SVG icon set - kept dependency-free rather than pulling in an
// icon library for a handful of glyphs.

const base = {
  width: "1em",
  height: "1em",
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.8,
  strokeLinecap: "round",
  strokeLinejoin: "round",
};

export function SendIcon(props) {
  return (
    <svg {...base} {...props}>
      <path d="M4 12L20 4L13 20L11 13L4 12Z" />
    </svg>
  );
}

export function PlusIcon(props) {
  return (
    <svg {...base} {...props}>
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

export function SparkleIcon(props) {
  return (
    <svg {...base} {...props}>
      <path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3z" />
    </svg>
  );
}

export function CheckIcon(props) {
  return (
    <svg {...base} {...props}>
      <path d="M5 13l4 4L19 7" />
    </svg>
  );
}

export function XIcon(props) {
  return (
    <svg {...base} {...props}>
      <path d="M18 6L6 18M6 6l12 12" />
    </svg>
  );
}

export function ShieldIcon(props) {
  return (
    <svg {...base} {...props}>
      <path d="M12 3l7 3v6c0 4.5-3 8-7 9-4-1-7-4.5-7-9V6l7-3z" />
    </svg>
  );
}

export function LogoutIcon(props) {
  return (
    <svg {...base} {...props}>
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9" />
    </svg>
  );
}

export function UploadIcon(props) {
  return (
    <svg {...base} {...props}>
      <path d="M12 16V4M7 9l5-5 5 5M4 20h16" />
    </svg>
  );
}

export function LinkIcon(props) {
  return (
    <svg {...base} {...props}>
      <path d="M9.5 14.5l5-5M8 17H6a4 4 0 0 1 0-8h2M16 7h2a4 4 0 0 1 0 8h-2" />
    </svg>
  );
}

export function EditIcon(props) {
  return (
    <svg {...base} {...props}>
      <path d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z" />
    </svg>
  );
}

export function MailIcon(props) {
  return (
    <svg {...base} {...props}>
      <path d="M4 5h16a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1z" />
      <path d="M3.5 6.5l8.5 6 8.5-6" />
    </svg>
  );
}

export function LockIcon(props) {
  return (
    <svg {...base} {...props}>
      <rect x="5" y="11" width="14" height="9" rx="1.5" />
      <path d="M8 11V8a4 4 0 0 1 8 0v3" />
    </svg>
  );
}

export function SunIcon(props) {
  return (
    <svg {...base} {...props}>
      <circle cx="12" cy="12" r="4.2" />
      <path d="M12 3v2M12 19v2M4.6 4.6l1.4 1.4M18 18l1.4 1.4M3 12h2M19 12h2M4.6 19.4L6 18M18 6l1.4-1.4" />
    </svg>
  );
}

export function MoonIcon(props) {
  return (
    <svg {...base} {...props}>
      <path d="M20 14.5A8.5 8.5 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z" />
    </svg>
  );
}

export function FileIcon(props) {
  return (
    <svg {...base} {...props}>
      <path d="M6 3h8l5 5v13a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z" />
      <path d="M14 3v5h5" />
    </svg>
  );
}

export function BarChartIcon(props) {
  return (
    <svg {...base} {...props}>
      <path d="M4 20V10M10 20V4M16 20V13M22 20V7M2 20h20" />
    </svg>
  );
}

export function LineChartIcon(props) {
  return (
    <svg {...base} {...props}>
      <path d="M3 17l5-6 4 3 6-9 3 4" />
      <path d="M3 20h18" />
    </svg>
  );
}

export function ScatterIcon(props) {
  return (
    <svg {...base} {...props}>
      <path d="M4 19L20 5" strokeDasharray="1.5 3" />
      <circle cx="6" cy="17" r="1.1" fill="currentColor" stroke="none" />
      <circle cx="9.5" cy="12.5" r="1.1" fill="currentColor" stroke="none" />
      <circle cx="13" cy="14" r="1.1" fill="currentColor" stroke="none" />
      <circle cx="16" cy="8" r="1.1" fill="currentColor" stroke="none" />
      <circle cx="19" cy="6.5" r="1.1" fill="currentColor" stroke="none" />
    </svg>
  );
}

export function PieChartIcon(props) {
  return (
    <svg {...base} {...props}>
      <path d="M12 3v9l7.5 4.3A9 9 0 1 0 12 3z" />
      <path d="M12 12L4.5 7.7" />
    </svg>
  );
}

export function NetworkIcon(props) {
  return (
    <svg {...base} {...props}>
      <circle cx="6" cy="6" r="2" />
      <circle cx="18" cy="6" r="2" />
      <circle cx="12" cy="18" r="2" />
      <circle cx="12" cy="11" r="1.7" />
      <path d="M7.6 7.2L10.6 10M16.4 7.2L13.4 10M12 12.7V16" />
    </svg>
  );
}

export function TrendUpIcon(props) {
  return (
    <svg {...base} {...props}>
      <path d="M3 16l6-6 4 4 8-9" />
      <path d="M14 5h7v7" />
    </svg>
  );
}

export function CandlestickIcon(props) {
  return (
    <svg {...base} {...props}>
      <path d="M6 4v4M6 14v6M18 3v5M18 15v6" />
      <rect x="4" y="8" width="4" height="6" />
      <rect x="16" y="8" width="4" height="7" />
      <path d="M12 6v3M12 17v1" />
      <rect x="10" y="9" width="4" height="8" />
    </svg>
  );
}

export function MatrixIcon(props) {
  return (
    <svg {...base} {...props}>
      <path d="M7 3H4v18h3M17 3h3v18h-3" />
      <circle cx="9" cy="8" r="0.9" fill="currentColor" stroke="none" />
      <circle cx="13" cy="8" r="0.9" fill="currentColor" stroke="none" />
      <circle cx="9" cy="12" r="0.9" fill="currentColor" stroke="none" />
      <circle cx="13" cy="12" r="0.9" fill="currentColor" stroke="none" />
      <circle cx="9" cy="16" r="0.9" fill="currentColor" stroke="none" />
      <circle cx="13" cy="16" r="0.9" fill="currentColor" stroke="none" />
    </svg>
  );
}

export function DatabaseIcon(props) {
  return (
    <svg {...base} {...props}>
      <ellipse cx="12" cy="5" rx="8" ry="3" />
      <path d="M4 5v14c0 1.66 3.58 3 8 3s8-1.34 8-3V5" />
      <path d="M4 12c0 1.66 3.58 3 8 3s8-1.34 8-3" />
    </svg>
  );
}

export function FunnelIcon(props) {
  return (
    <svg {...base} {...props}>
      <path d="M3 4h18l-7 8v6l-4 2v-8L3 4z" />
    </svg>
  );
}
