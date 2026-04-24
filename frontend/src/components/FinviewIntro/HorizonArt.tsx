import { Bloom } from './Bloom';

type HorizonArtProps = { replaying: number };

export function HorizonArt({ replaying }: HorizonArtProps) {
  const branches = [
    { d: 'M250,284 C248,260 258,244 252,220', delay: 2400 },
    { d: 'M430,248 C428,220 440,200 432,176', delay: 2700 },
    { d: 'M610,196 C608,168 622,148 616,122', delay: 3000 },
    { d: 'M790,138 C788,108 802,88 796,62',  delay: 3300 },
    { d: 'M960,78 C960,54 974,34 970,14',    delay: 3600 },
  ];

  const blooms = [
    { cx: 252, cy: 220, size: 0.8,  delay: 3600 },
    { cx: 432, cy: 176, size: 0.9,  delay: 3850 },
    { cx: 616, cy: 122, size: 1.0,  delay: 4100 },
    { cx: 796, cy: 62,  size: 1.1,  delay: 4350 },
    { cx: 970, cy: 14,  size: 1.25, delay: 4600 },
  ];

  const pollen = [
    { cx: 320, cy: 200, r: 2,   delay: 4200 },
    { cx: 540, cy: 140, r: 2.2, delay: 4700 },
    { cx: 720, cy: 110, r: 1.8, delay: 5100 },
    { cx: 880, cy: 60,  r: 2.4, delay: 5400 },
  ];

  return (
    <svg
      key={replaying}
      viewBox="0 0 1100 360"
      preserveAspectRatio="xMidYMid meet"
      aria-hidden="true"
      style={{ width: '100%', height: '100%', display: 'block', overflow: 'visible' }}
    >
      <line x1="40" y1="320" x2="1060" y2="320"
        stroke="rgba(31,27,22,0.10)" strokeWidth="1" strokeDasharray="2 5" />

      {/* Seed */}
      <circle cx="80" cy="320" r="7"
        fill="var(--fv-ochre, #9A6B1F)"
        style={{
          transformBox: 'fill-box', transformOrigin: 'center', transform: 'scale(0)',
          animation: 'fv-pop 600ms cubic-bezier(0.2,0.8,0.2,1) 400ms forwards',
        }}
      />

      {/* Ascending trunk */}
      <path
        d="M80,320 C140,318 180,306 220,294 C270,278 300,280 340,266 C390,248 420,252 470,234 C530,212 560,216 610,196 C670,172 700,176 750,152 C810,124 840,128 890,104 C940,80 970,82 1020,60"
        fill="none" stroke="var(--fv-ink, #1F1B16)" strokeWidth="3" strokeLinecap="round"
        style={{
          strokeDasharray: 1400, strokeDashoffset: 1400,
          animation: 'fv-draw-long 2400ms cubic-bezier(0.2,0.8,0.2,1) 600ms forwards',
        }}
      />

      {/* Vertical branches */}
      {branches.map(({ d, delay }, i) => (
        <path key={i} d={d}
          fill="none" stroke="rgba(31,27,22,0.7)" strokeWidth="2" strokeLinecap="round"
          style={{
            strokeDasharray: 300, strokeDashoffset: 300,
            animation: `fv-draw 1000ms cubic-bezier(0.2,0.8,0.2,1) ${delay}ms forwards`,
          }}
        />
      ))}

      {/* Blooms — grow larger left to right */}
      {blooms.map(({ cx, cy, size, delay }) => (
        <Bloom key={cx} cx={cx} cy={cy} size={size} petalCount={5} animDelay={delay} />
      ))}

      {/* Pollen */}
      {pollen.map(({ cx, cy, r, delay }) => (
        <circle key={cx} cx={cx} cy={cy} r={r}
          fill="var(--fv-ochre, #9A6B1F)"
          style={{
            opacity: 0,
            animation: `fv-drift 4200ms cubic-bezier(0.2,0.8,0.2,1) ${delay}ms infinite`,
          }}
        />
      ))}
    </svg>
  );
}
