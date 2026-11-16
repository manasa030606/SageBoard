import { cn } from "@/lib/cn";

/*
 * Decorative illustration for the sign-in panel: raw data (left) flows through an AI core
 * (middle) and comes out as a chart and an insight (right). Inline SVG in the brand colours,
 * animated with CSS only (see `.sb-illo` in globals.css): no image file, no script, no network.
 * It holds no figures of its own: every bar, line and row is abstract.
 *
 * Every shape is drawn in its finished state; the animations only run for people who haven't
 * asked for reduced motion, so the picture is complete either way.
 */
const BARS = [
  { h: 18, delay: 0 },
  { h: 28, delay: 0.12 },
  { h: 22, delay: 0.24 },
  { h: 38, delay: 0.36 },
  { h: 32, delay: 0.48 },
  { h: 52, delay: 0.6 },
];
const BASELINE = 168;
const ROWS = [0, 1, 2, 3, 4, 5];
const PARTICLES = [
  { x: 34, y: 44, r: 2.5, d: 0, t: 6 },
  { x: 78, y: 30, r: 1.5, d: 1.2, t: 7.5 },
  { x: 160, y: 62, r: 2, d: 2.1, t: 6.5 },
  { x: 246, y: 24, r: 2, d: 0.6, t: 8 },
  { x: 146, y: 244, r: 2.5, d: 1.8, t: 7 },
  { x: 62, y: 268, r: 2, d: 0.3, t: 6.8 },
  { x: 214, y: 262, r: 1.5, d: 2.6, t: 7.2 },
  { x: 14, y: 156, r: 1.5, d: 1.5, t: 8.2 },
];

export function AnalyticsIllustration({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 480 310"
      role="presentation"
      aria-hidden
      focusable="false"
      preserveAspectRatio="xMinYMid meet"
      className={cn("sb-illo block h-full w-full", className)}
    >
      <defs>
        <linearGradient id="sb-area" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="var(--color-sage)" stopOpacity="0.38" />
          <stop offset="1" stopColor="var(--color-sage)" stopOpacity="0" />
        </linearGradient>
        <radialGradient id="sb-glow" cx="0.5" cy="0.5" r="0.5">
          <stop offset="0" stopColor="var(--color-sage)" stopOpacity="0.3" />
          <stop offset="1" stopColor="var(--color-sage)" stopOpacity="0" />
        </radialGradient>
      </defs>

      <circle cx="380" cy="150" r="150" fill="url(#sb-glow)" opacity="0.6" />

      {/* Floating data points */}
      {PARTICLES.map((p) => (
        <circle
          key={`${p.x}-${p.y}`}
          className="sb-float"
          cx={p.x}
          cy={p.y}
          r={p.r}
          fill="var(--color-sage)"
          fillOpacity="0.55"
          style={{ animationDelay: `${p.d}s`, animationDuration: `${p.t}s` }}
        />
      ))}

      {/* 1. Raw data */}
      <g>
        <rect
          x="8"
          y="76"
          width="104"
          height="156"
          rx="12"
          fill="var(--color-navy-700)"
          stroke="var(--color-warm)"
          strokeOpacity="0.16"
        />
        <rect
          x="20"
          y="90"
          width="48"
          height="6"
          rx="3"
          fill="var(--color-warm)"
          fillOpacity="0.5"
        />
        <line x1="8" x2="112" y1="104" y2="104" stroke="var(--color-warm)" strokeOpacity="0.1" />
        {ROWS.map((i) => (
          <g key={i} className="sb-row" style={{ animationDelay: `${i * 0.35}s` }}>
            <rect
              x="20"
              y={114 + i * 18}
              width="26"
              height="6"
              rx="3"
              fill="var(--color-warm)"
              fillOpacity="0.4"
            />
            <rect
              x="54"
              y={114 + i * 18}
              width="40"
              height="6"
              rx="3"
              fill="var(--color-warm)"
              fillOpacity="0.2"
            />
          </g>
        ))}
        <rect
          className="sb-scan"
          x="14"
          y="110"
          width="92"
          height="14"
          rx="4"
          fill="var(--color-sage)"
          fillOpacity="0.16"
        />
        <text x="60" y="252" textAnchor="middle" className="sb-label">
          DATA
        </text>
      </g>

      {/* Data flowing into the AI core */}
      <g
        fill="none"
        stroke="var(--color-sage)"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeDasharray="3 6"
        strokeOpacity="0.7"
      >
        <path className="sb-flow" d="M112 130 C140 130 150 154 178 154" />
        <path className="sb-flow" d="M112 154 L178 154" />
        <path className="sb-flow" d="M112 178 C140 178 150 154 178 154" />
      </g>

      {/* 2. AI core */}
      <g>
        <circle className="sb-glow" cx="210" cy="154" r="46" fill="url(#sb-glow)" />
        <circle
          className="sb-ring"
          cx="210"
          cy="154"
          r="30"
          fill="none"
          stroke="var(--color-sage)"
          strokeOpacity="0.4"
        />
        <g className="sb-spin">
          <circle
            cx="210"
            cy="154"
            r="24"
            fill="none"
            stroke="var(--color-sage)"
            strokeOpacity="0.55"
            strokeDasharray="2 5"
            strokeLinecap="round"
          />
          <circle cx="234" cy="154" r="2.5" fill="var(--color-sage)" />
          <circle cx="186" cy="154" r="2" fill="var(--color-sage)" fillOpacity="0.7" />
        </g>
        <circle
          cx="210"
          cy="154"
          r="16"
          fill="var(--color-forest)"
          stroke="var(--color-sage)"
          strokeWidth="1.5"
        />
        <path
          className="sb-spark"
          d="M210 144 l2.8 7 7 2.8 -7 2.8 -2.8 7 -2.8 -7 -7 -2.8 7 -2.8 z"
          fill="var(--color-sage)"
        />
        <text x="210" y="212" textAnchor="middle" className="sb-label">
          AI
        </text>
      </g>

      {/* Analysis flowing out to the dashboard */}
      <path
        className="sb-flow"
        d="M242 154 L272 154"
        fill="none"
        stroke="var(--color-sage)"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeDasharray="3 6"
        strokeOpacity="0.7"
      />

      {/* 3. Insights: dashboard */}
      <g>
        <rect
          x="272"
          y="44"
          width="200"
          height="212"
          rx="14"
          fill="var(--color-navy-700)"
          stroke="var(--color-warm)"
          strokeOpacity="0.16"
        />
        <circle cx="288" cy="60" r="3" fill="var(--color-warm)" fillOpacity="0.3" />
        <circle cx="299" cy="60" r="3" fill="var(--color-warm)" fillOpacity="0.3" />
        <circle cx="310" cy="60" r="3" fill="var(--color-warm)" fillOpacity="0.3" />
        <line x1="272" x2="472" y1="74" y2="74" stroke="var(--color-warm)" strokeOpacity="0.1" />
        <rect
          x="288"
          y="86"
          width="72"
          height="6"
          rx="3"
          fill="var(--color-warm)"
          fillOpacity="0.5"
        />
        <rect
          x="288"
          y="98"
          width="44"
          height="4"
          rx="2"
          fill="var(--color-warm)"
          fillOpacity="0.2"
        />

        <line
          x1="288"
          x2="456"
          y1={BASELINE}
          y2={BASELINE}
          stroke="var(--color-warm)"
          strokeOpacity="0.14"
        />
        {BARS.map((b, i) => (
          <rect
            key={i}
            className="sb-bar"
            x={288 + i * 18}
            y={BASELINE - b.h}
            width="12"
            height={b.h}
            rx="3"
            fill={i === BARS.length - 1 ? "var(--color-sage)" : "var(--color-forest)"}
            style={{ animationDelay: `${b.delay}s` }}
          />
        ))}

        <path
          className="sb-area"
          d="M288 232 L318 220 L346 226 L376 206 L406 212 L436 192 L456 196 L456 238 L288 238 Z"
          fill="url(#sb-area)"
        />
        <path
          className="sb-line"
          pathLength="1"
          d="M288 232 L318 220 L346 226 L376 206 L406 212 L436 192 L456 196"
          fill="none"
          stroke="var(--color-sage)"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <circle
          className="sb-dot"
          cx="456"
          cy="196"
          r="4.5"
          fill="var(--color-navy-700)"
          stroke="var(--color-sage)"
          strokeWidth="2.5"
        />
        <line x1="288" x2="456" y1="238" y2="238" stroke="var(--color-warm)" strokeOpacity="0.14" />
        <text x="472" y="34" textAnchor="end" className="sb-label">
          INSIGHTS
        </text>
      </g>

      {/* Insight card */}
      <g>
        <rect
          x="292"
          y="250"
          width="180"
          height="48"
          rx="12"
          fill="var(--color-warm)"
          stroke="var(--color-navy)"
          strokeOpacity="0.1"
        />
        <rect
          className="sb-glow"
          x="302"
          y="259"
          width="30"
          height="30"
          rx="9"
          fill="var(--color-sage)"
          fillOpacity="0.5"
        />
        <rect x="304" y="261" width="26" height="26" rx="8" fill="var(--color-forest)" />
        <path
          className="sb-spark"
          d="M317 266 l2.4 5.8 5.8 2.4 -5.8 2.4 -2.4 5.8 -2.4 -5.8 -5.8 -2.4 5.8 -2.4 z"
          fill="var(--color-sage)"
        />
        <rect
          x="342"
          y="263"
          width="108"
          height="7"
          rx="3.5"
          fill="var(--color-navy)"
          fillOpacity="0.8"
        />
        <rect
          x="342"
          y="277"
          width="76"
          height="5"
          rx="2.5"
          fill="var(--color-navy)"
          fillOpacity="0.3"
        />
      </g>
    </svg>
  );
}
