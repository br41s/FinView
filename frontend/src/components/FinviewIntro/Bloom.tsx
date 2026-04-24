type BloomProps = {
  cx: number;
  cy: number;
  size?: number;
  petalCount?: number;
  animDelay?: number;
  className?: string;
};

export function Bloom({ cx, cy, size = 1, petalCount = 5, animDelay = 0, className = '' }: BloomProps) {
  const r = size;
  const angles = Array.from({ length: petalCount }, (_, i) => (360 / petalCount) * i);

  return (
    <g
      className={`fv-bloom ${className}`.trim()}
      transform={`translate(${cx} ${cy})`}
      style={{ cursor: 'pointer' }}
    >
      <g
        className="bloom-sway"
        style={{
          transformBox: 'fill-box',
          transformOrigin: 'center bottom',
          animation: `fv-sway 5s cubic-bezier(0.2,0.8,0.2,1) ${animDelay + 4600}ms infinite`,
        }}
      >
        {/* Hover outer petals */}
        <g className="petal-outer">
          {angles.map((angle) => (
            <ellipse
              key={angle}
              cx={0} cy={-14 * r} rx={4 * r} ry={10 * r}
              fill="var(--fv-ochre-soft, #D4B07A)"
              transform={`rotate(${angle})`}
            />
          ))}
        </g>

        {/* Base petals */}
        <g
          className="petal"
          style={{
            fill: 'var(--fv-ochre, #9A6B1F)',
            transformBox: 'fill-box',
            transformOrigin: 'center bottom',
            transform: 'scale(0)',
            animation: `fv-petal 520ms cubic-bezier(0.2,0.8,0.2,1) ${animDelay}ms forwards`,
          }}
        >
          {angles.map((angle) => (
            <ellipse
              key={angle}
              cx={0} cy={-10 * r} rx={5 * r} ry={9 * r}
              transform={`rotate(${angle})`}
            />
          ))}
        </g>

        {/* Inner disc */}
        <circle
          className="petal-inner"
          r={5 * r} cx={0} cy={0}
          fill="var(--fv-ochre, #9A6B1F)"
          style={{
            transform: 'scale(0)',
            transformBox: 'fill-box',
            transformOrigin: 'center',
            animation: `fv-petal-inner 520ms cubic-bezier(0.2,0.8,0.2,1) ${animDelay + 150}ms forwards`,
          }}
        />

        {/* Core */}
        <circle
          className="core"
          r={2.5 * r} cx={0} cy={0}
          fill="var(--fv-paper, #F5F1E8)"
          stroke="var(--fv-ochre-dark, #825416)"
          strokeWidth={1.5}
          style={{
            transform: 'scale(0)',
            transformBox: 'fill-box',
            transformOrigin: 'center',
            animation: `fv-core 420ms cubic-bezier(0.2,0.8,0.2,1) ${animDelay + 250}ms forwards`,
          }}
        />
      </g>
    </g>
  );
}
