import type { SVGProps } from 'react';

// Minimal inline SVG icon set for the floating background motifs and the
// theme toggle - kept dependency-free rather than pulling in an icon library
// for a handful of glyphs.

const base: SVGProps<SVGSVGElement> = {
  width: '1em',
  height: '1em',
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.8,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
};

export function SunIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} {...props}>
      <circle cx="12" cy="12" r="4.2" />
      <path d="M12 3v2M12 19v2M4.6 4.6l1.4 1.4M18 18l1.4 1.4M3 12h2M19 12h2M4.6 19.4L6 18M18 6l1.4-1.4" />
    </svg>
  );
}

export function MoonIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} {...props}>
      <path d="M20 14.5A8.5 8.5 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z" />
    </svg>
  );
}

// The ten motifs below share one grid so they carry equal optical weight at
// the same font-size: every drawing is centred on (12, 12) and stays inside
// x/y 3..21. The previous set drifted between 2..22 and 4..22, which made some
// of them read as heavier or visibly off-centre against the others.

export function BarChartIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} {...props}>
      {/* Bars at 6/10/14/18 and a baseline of 3..21 share the same midpoint,
          and the tallest bar reaches y=4 so the drawing is centred vertically
          too rather than sitting low in the box. */}
      <path d="M3 20h18" />
      <path d="M6 20v-6M10 20v-12M14 20v-9M18 20v-16" />
    </svg>
  );
}

export function LineChartIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} {...props}>
      <path d="M4 4v16h16" />
      <path d="M7.5 16l3.5-4.5 3.5 2.5L19 7" />
    </svg>
  );
}

export function ScatterIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} {...props}>
      {/* Axes plus points, and no regression line: a dashed line at this size
          renders as a row of dashes indistinguishable from the data points, so
          the two together read as one shapeless cluster. */}
      <path d="M4 4v16h16" />
      <circle cx="7.5" cy="16.5" r="1.2" fill="currentColor" stroke="none" />
      <circle cx="11" cy="12.5" r="1.2" fill="currentColor" stroke="none" />
      <circle cx="11.5" cy="17.5" r="1.2" fill="currentColor" stroke="none" />
      <circle cx="15" cy="8.5" r="1.2" fill="currentColor" stroke="none" />
      <circle cx="15.5" cy="14" r="1.2" fill="currentColor" stroke="none" />
      <circle cx="18.5" cy="10.5" r="1.2" fill="currentColor" stroke="none" />
    </svg>
  );
}

export function PieChartIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} {...props}>
      {/* A plain circle plus two radii. The previous version used an arc whose
          end point was 8.65 from the centre while declaring r=9, so the
          renderer scaled the radius up to make it reach and the circle came
          out visibly distorted. */}
      <circle cx="12" cy="12" r="9" />
      <path d="M12 12V3" />
      <path d="M12 12l7.8 4.5" />
    </svg>
  );
}

export function NetworkIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} {...props}>
      {/* All five nodes share one radius; edges stop at the node edge rather
          than running under it. */}
      <circle cx="12" cy="12" r="2" />
      <circle cx="6" cy="7" r="2" />
      <circle cx="18" cy="7" r="2" />
      <circle cx="6" cy="17" r="2" />
      <circle cx="18" cy="17" r="2" />
      <path d="M10.5 10.7L7.5 8.3M13.5 10.7L16.5 8.3M10.5 13.3L7.5 15.7M13.5 13.3L16.5 15.7" />
    </svg>
  );
}

export function TrendUpIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} {...props}>
      <path d="M4 17l5-5 4 3 7-8" />
      <path d="M15 7h5v5" />
    </svg>
  );
}

export function CandlestickIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} {...props}>
      {/* Bodies are filled rather than outlined. At 4 units wide against a 1.8
          stroke an outlined body has almost no interior left, so the three
          candles ran together into one indistinct block. Filling them also
          matches how a real chart distinguishes a body from its wick. */}
      <path d="M6 4v3.5M6 15.5v4M12 5v3M12 16v4M18 6.5v4M18 18v2" />
      <rect x="4.4" y="7.5" width="3.2" height="8" rx="0.6" fill="currentColor" stroke="none" />
      <rect x="10.4" y="8" width="3.2" height="8" rx="0.6" fill="currentColor" stroke="none" />
      <rect x="16.4" y="10.5" width="3.2" height="7.5" rx="0.6" fill="currentColor" stroke="none" />
    </svg>
  );
}

export function MatrixIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} {...props}>
      {/* Columns at 9.5/14.5 and rows at 8/12/16 share the brackets' centre.
          The dots previously sat at 9/13, one unit left of it, and too close
          together to fill the space between the brackets. */}
      <path d="M8 4H5v16h3M16 4h3v16h-3" />
      <circle cx="9.5" cy="8" r="1.1" fill="currentColor" stroke="none" />
      <circle cx="14.5" cy="8" r="1.1" fill="currentColor" stroke="none" />
      <circle cx="9.5" cy="12" r="1.1" fill="currentColor" stroke="none" />
      <circle cx="14.5" cy="12" r="1.1" fill="currentColor" stroke="none" />
      <circle cx="9.5" cy="16" r="1.1" fill="currentColor" stroke="none" />
      <circle cx="14.5" cy="16" r="1.1" fill="currentColor" stroke="none" />
    </svg>
  );
}

export function DatabaseIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} {...props}>
      <ellipse cx="12" cy="6" rx="7" ry="3" />
      <path d="M5 6v12c0 1.66 3.13 3 7 3s7-1.34 7-3V6" />
      <path d="M5 12c0 1.66 3.13 3 7 3s7-1.34 7-3" />
    </svg>
  );
}

export function FunnelIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} {...props}>
      <path d="M4 5h16l-6 7v7l-4-2v-5L4 5z" />
    </svg>
  );
}
