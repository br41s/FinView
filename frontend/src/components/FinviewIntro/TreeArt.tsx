import { Bloom } from './Bloom';

type TreeArtProps = { replaying: number };

export function TreeArt({ replaying }: TreeArtProps) {
  const leaves = [
    { cx: 395, cy: 318, angle: -20, delay: 2400 },
    { cx: 215, cy: 225, angle: 10,  delay: 2700 },
    { cx: 370, cy: 170, angle: -10, delay: 3000 },
    { cx: 285, cy: 120, angle: 15,  delay: 3300 },
  ];

  const pollen = [
    { cx: 220, cy: 250, r: 2,   delay: 3400 },
    { cx: 360, cy: 180, r: 2.5, delay: 3900 },
    { cx: 300, cy: 300, r: 1.8, delay: 4300 },
  ];

  return (
    <svg
      key={replaying}
      viewBox="0 0 560 590"
      preserveAspectRatio="xMidYMid meet"
      aria-hidden="true"
      style={{ width: '100%', height: '100%', display: 'block', overflow: 'visible' }}
    >
      {/* Ground line */}
      <line x1="60" y1="555" x2="500" y2="555"
        stroke="rgba(31,27,22,0.12)" strokeWidth="1" strokeDasharray="2 4" />

      {/* Seed */}
      <circle cx="280" cy="555" r="6"
        fill="var(--fv-ochre, #9A6B1F)"
        style={{
          transformBox: 'fill-box', transformOrigin: 'center',
          transform: 'scale(0)',
          animation: 'fv-pop 500ms cubic-bezier(0.2,0.8,0.2,1) 300ms forwards',
        }}
      />

      {/* Trunk */}
      <path
        d="M280,555 C282,500 270,460 278,420 C286,380 274,340 282,300 C290,260 276,220 288,180 C294,150 286,120 292,95"
        fill="none" stroke="var(--fv-ink, #1F1B16)" strokeWidth="3.5" strokeLinecap="round"
        style={{
          strokeDasharray: 900, strokeDashoffset: 900,
          animation: 'fv-draw 1400ms cubic-bezier(0.2,0.8,0.2,1) 500ms forwards',
        }}
      />

      {/* Branch b2 — right mid */}
      <path
        d="M282,360 C320,352 360,340 400,312 C418,300 426,284 430,264"
        fill="none" stroke="rgba(31,27,22,0.7)" strokeWidth="2.5" strokeLinecap="round"
        style={{
          strokeDasharray: 400, strokeDashoffset: 400,
          animation: 'fv-draw 800ms cubic-bezier(0.2,0.8,0.2,1) 1900ms forwards',
        }}
      />

      {/* Branch b3 — left high */}
      <path
        d="M284,280 C256,270 230,252 210,222 C200,208 198,190 202,170"
        fill="none" stroke="rgba(31,27,22,0.7)" strokeWidth="2.5" strokeLinecap="round"
        style={{
          strokeDasharray: 400, strokeDashoffset: 400,
          animation: 'fv-draw 800ms cubic-bezier(0.2,0.8,0.2,1) 2200ms forwards',
        }}
      />

      {/* Branch b4 — right high */}
      <path
        d="M288,220 C320,210 352,192 374,162 C384,148 388,130 386,112"
        fill="none" stroke="rgba(31,27,22,0.7)" strokeWidth="2.5" strokeLinecap="round"
        style={{
          strokeDasharray: 400, strokeDashoffset: 400,
          animation: 'fv-draw 800ms cubic-bezier(0.2,0.8,0.2,1) 2500ms forwards',
        }}
      />

      {/* Leaves */}
      {leaves.map(({ cx, cy, angle, delay }) => (
        <ellipse key={`${cx}-${cy}`}
          cx={cx} cy={cy} rx="5" ry="3"
          fill="var(--fv-ink, #1F1B16)"
          transform={`rotate(${angle} ${cx} ${cy})`}
          style={{
            opacity: 0,
            transformBox: 'fill-box', transformOrigin: 'center',
            animation: `fv-leaf-in 400ms cubic-bezier(0.2,0.8,0.2,1) ${delay}ms forwards`,
          }}
        />
      ))}

      {/* Blooms */}
      <Bloom cx={430} cy={264} size={1}   petalCount={6} animDelay={3400} />
      <Bloom cx={202} cy={170} size={1}   petalCount={5} animDelay={3650} />
      <Bloom cx={386} cy={112} size={1}   petalCount={5} animDelay={3900} />
      <Bloom cx={292} cy={95}  size={1.3} petalCount={6} animDelay={4150} />

      {/* Pollen drift */}
      {pollen.map(({ cx, cy, r, delay }) => (
        <circle key={`d-${cx}`} cx={cx} cy={cy} r={r}
          fill="var(--fv-ochre, #9A6B1F)"
          style={{
            opacity: 0,
            animation: `fv-drift 3200ms cubic-bezier(0.2,0.8,0.2,1) ${delay}ms infinite`,
          }}
        />
      ))}
    </svg>
  );
}
