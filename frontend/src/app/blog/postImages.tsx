import type { PostSlug } from './posts';
import styles from './blog.module.css';

/**
 * The card illustration for every article, keyed by slug.
 *
 * These 60 hand-drawn SVGs used to sit inline in `page.tsx`, interleaved with
 * the post data and the page itself in a single 2,321-line file. They are the
 * bulk of it and they change for one reason only — a new article — so they live
 * on their own here.
 *
 * Typing the map as `Record<PostSlug, PostImage>` is what makes the coverage a
 * compile error rather than a blank card: adding a post to `POST_META` without
 * drawing it fails `tsc`, and so does an illustration whose slug no longer
 * exists.
 */
export type PostImage = () => React.ReactElement;

/** Bars for ImgYoc — a lookup keeps the SVG readable. */
type YocBar = { label: string; value: string; faded: boolean; hClass: 'yocBarH60' | 'yocBarH112' };
const YOC_BARS: YocBar[] = [
  { label: 'YOP', value: '3.1%', faded: true,  hClass: 'yocBarH60'  },
  { label: 'YOC', value: '8.4%', faded: false, hClass: 'yocBarH112' },
];

function ImgAmortizarHipotecaVsInvertir() {
  return (
    <div className={styles.postImgAmortizarHipotecaVsInvertir}>
      <svg viewBox="0 0 200 120" width="200" height="120" fill="none" aria-hidden="true">
        <text x="100" y="20" fontSize="8" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle" letterSpacing="0.08em">AMORTIZAR vs INVERTIR</text>
        {/* Savings source */}
        <rect x="62" y="32" width="76" height="20" rx="4" stroke="var(--fv-ink-30)" strokeWidth="1.5" fill="none"/>
        <text x="100" y="46" fontSize="7" fill="var(--fv-ink)" fontFamily="system-ui" textAnchor="middle">TUS AHORROS</text>
        {/* Split paths */}
        <path d="M100,52 L100,62 L45,62 L45,74" stroke="var(--fv-ochre)" strokeWidth="1.5" fill="none"/>
        <path d="M100,52 L100,62 L155,62 L155,74" stroke="var(--fv-ink-40)" strokeWidth="1.5" fill="none"/>
        {/* House (amortizar) */}
        <polygon points="28,96 45,82 62,96" stroke="var(--fv-ochre)" strokeWidth="1.5" fill="var(--fv-ochre-ghost)"/>
        <rect x="33" y="95" width="24" height="18" stroke="var(--fv-ochre)" strokeWidth="1.5" fill="var(--fv-ochre-ghost)"/>
        <text x="45" y="76" fontSize="6" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">AMORTIZAR</text>
        <text x="45" y="118" fontSize="6" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">3% garantizado</text>
        {/* Dividend coins (invertir) */}
        <circle cx="155" cy="96" r="7" stroke="var(--fv-ink-30)" strokeWidth="1.5" fill="none"/>
        <circle cx="155" cy="86" r="7" stroke="var(--fv-ink-30)" strokeWidth="1.5" fill="none"/>
        <circle cx="155" cy="76" r="7" fill="var(--fv-ochre-ghost)" stroke="var(--fv-ochre)" strokeWidth="1.5"/>
        <text x="155" y="79" fontSize="6" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">€</text>
        <text x="155" y="66" fontSize="6" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">INVERTIR</text>
        <text x="155" y="118" fontSize="6" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">8% + dividendo</text>
      </svg>
    </div>
  );
}

function ImgAnalisisSectorial() {
  const sectors = ['Banca', 'Energía', 'Utilities', 'Infra.', 'Consumo'];
  const yields = [8, 18, 14, 10, 6];
  const maxH = Math.max(...yields);
  const sectorColors = ['rgba(154,107,31,0.25)', 'var(--fv-ochre)', 'rgba(154,107,31,0.35)', 'rgba(154,107,31,0.20)', 'rgba(154,107,31,0.15)'];
  return (
    <div className={styles.postImgAnalisisSectorial}>
      <svg viewBox="0 0 200 120" width="200" height="120" fill="none" aria-hidden="true">
        <text x="100" y="14" fontSize="7" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle" letterSpacing="0.08em">RENTABILIDAD POR SECTOR — 2026</text>
        {sectors.map((s, i) => {
          const x = 20 + i * 36;
          const h = Math.round((yields[i] / maxH) * 60);
          return (
            <g key={s}>
              <rect x={x} y={105 - h} width="22" height={h} rx="3" fill={sectorColors[i]} />
              <text x={x + 11} y={116} fontSize="5" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">{s}</text>
            </g>
          );
        })}
        <circle cx="36" cy="64" r="12" fill="none" stroke="var(--fv-ochre)" strokeWidth="1" opacity="0.4" />
        <circle cx="108" cy="64" r="12" fill="none" stroke="var(--fv-ochre)" strokeWidth="1" opacity="0.4" />
        <line x1="8" y1="45" x2="192" y2="45" stroke="var(--fv-ink-15)" strokeWidth="0.8" strokeDasharray="2 3" />
        <text x="100" y="42" fontSize="5" fill="var(--fv-ink-30)" fontFamily="system-ui" textAnchor="middle">visibilidad media</text>
      </svg>
    </div>
  );
}

function ImgAportacionesPeriodicas() {
  return (
    <div className={styles.postImgAportacionesPeriodicas}>
      <svg viewBox="0 0 200 120" width="200" height="120" fill="none" aria-hidden="true">
        <text x="100" y="14" fontSize="7" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle" letterSpacing="0.08em">APORTACIÓN PERIÓDICA · CADA MES</text>
        {/* Monthly contribution drops */}
        <circle cx="26" cy="26" r="7" fill="var(--fv-ochre-ghost)" stroke="var(--fv-ochre)" strokeWidth="1.5"/>
        <text x="26" y="29" fontSize="6" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">€</text>
        <circle cx="44" cy="38" r="7" fill="var(--fv-ochre-ghost)" stroke="var(--fv-ochre)" strokeWidth="1.5"/>
        <circle cx="62" cy="50" r="7" fill="var(--fv-ochre-ghost)" stroke="var(--fv-ochre)" strokeWidth="1.5"/>
        <circle cx="80" cy="62" r="7" fill="var(--fv-ochre-ghost)" stroke="var(--fv-ochre)" strokeWidth="1.5"/>
        <circle cx="98" cy="74" r="7" fill="var(--fv-ochre-ghost)" stroke="var(--fv-ochre)" strokeWidth="1.5"/>
        <path d="M98 74 L122 88" stroke="var(--fv-ochre)" strokeWidth="1.2" strokeDasharray="3 2"/>
        {/* Dividend snowball: growing staircase */}
        <rect x="124" y="88" width="14" height="16" fill="var(--fv-ochre-ghost)" stroke="var(--fv-ochre)" strokeWidth="1"/>
        <rect x="142" y="80" width="14" height="24" fill="var(--fv-ochre-ghost)" stroke="var(--fv-ochre)" strokeWidth="1"/>
        <rect x="160" y="70" width="14" height="34" fill="var(--fv-ochre)" rx="2"/>
        <rect x="178" y="56" width="14" height="48" fill="var(--fv-ochre)" rx="2"/>
        <text x="185" y="50" fontSize="7" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">€€</text>
        <text x="100" y="116" fontSize="5.5" fill="var(--fv-ink-30)" fontFamily="system-ui" textAnchor="middle">día fijo · importe fijo · el dividendo crece solo</text>
      </svg>
    </div>
  );
}

function ImgAristocratsEuropa() {
  return (
    <div className={styles.postImgAristocratsEuropa}>
      <svg viewBox="0 0 200 120" width="200" height="120" fill="none" aria-hidden="true">
        <text x="100" y="14" fontSize="7" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle" letterSpacing="0.08em">10+ AÑOS SUBIENDO EL DIVIDENDO</text>
        <polyline
          points="20,100 20,88 50,88 50,72 80,72 80,56 110,56 110,40 140,40 140,26 170,26"
          stroke="var(--fv-ochre)" strokeWidth="2.5" fill="none" strokeLinecap="round" strokeLinejoin="round"
        />
        {[[20,88],[50,72],[80,56],[110,40],[140,26],[170,26]].map(([x,y], i) => (
          <circle key={i} cx={x} cy={y} r="3" fill="var(--fv-ochre)" />
        ))}
        <line x1="20" y1="100" x2="180" y2="100" stroke="var(--fv-ink-30)" strokeWidth="1" strokeDasharray="4 3" />
        <text x="100" y="113" fontSize="6" fill="var(--fv-ink-30)" fontFamily="system-ui" textAnchor="middle">cada peldaño = un año más de dividendo mayor</text>
      </svg>
    </div>
  );
}

function ImgBonosRentaFija() {
  return (
    <div className={styles.postImgBonosRentaFija}>
      <svg viewBox="0 0 200 120" width="200" height="120" fill="none" aria-hidden="true">
        <text x="100" y="14" fontSize="7" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle" letterSpacing="0.08em">BONO · CUPÓN ANUAL</text>
        {/* Bond block */}
        <rect x="56" y="26" width="88" height="48" rx="6" stroke="var(--fv-ochre)" strokeWidth="1.5" fill="var(--fv-ochre-ghost)"/>
        <text x="100" y="45" fontSize="8" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">BONO</text>
        <text x="100" y="58" fontSize="7" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">3,5% anual</text>
        <text x="100" y="70" fontSize="6" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">10.000 €</text>
        {/* Coupon arrow down with 19% retention */}
        <line x1="100" y1="76" x2="100" y2="90" stroke="var(--fv-ink-30)" strokeWidth="1.5"/>
        <polygon points="95,86 105,86 100,94" fill="var(--fv-ink-30)"/>
        <text x="100" y="104" fontSize="6.5" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">Cupón 350 € · retención 19% = 66,5 €</text>
        <text x="100" y="114" fontSize="5.5" fill="var(--fv-ink-30)" fontFamily="system-ui" textAnchor="middle">declaras el bruto, no el neto</text>
      </svg>
    </div>
  );
}

function ImgBroker() {
  return (
    <div className={styles.postImgBroker}>
      <svg viewBox="0 0 200 120" width="200" height="120" fill="none" aria-hidden="true">
        {/* Laptop / Broker terminal */}
        <rect x="30" y="30" width="140" height="70" rx="8" stroke="var(--fv-ink-30)" strokeWidth="1.5" fill="none"/>
        <line x1="30" y1="55" x2="170" y2="55" stroke="var(--fv-ink-15)" strokeWidth="1"/>
        {/* Bars for comparison */}
        {[
          { x: 50, h: 30, label: 'TR' },
          { x: 90, h: 45, label: 'IBKR' },
          { x: 130, h: 20, label: 'DG' },
        ].map(({ x, h, label }) => (
          <g key={label}>
            <rect x={x} y={110 - h} width="20" height={h} fill="rgba(154,107,31,0.25)" rx="3"/>
            <rect x={x} y={110 - h} width="20" height={h * 0.3} fill="var(--fv-ochre)" rx="3"/>
            <text x={x + 10} y="118" fontSize="7" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">{label}</text>
          </g>
        ))}
        <text x="100" y="18" fontSize="7" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle" letterSpacing="0.08em">BROKER COMPARISON</text>
      </svg>
    </div>
  );
}

function ImgCalendarioDividendos() {
  const months = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic'];
  const dividends = [85, 120, 95, 110, 130, 280, 90, 45, 45, 140, 100, 40];
  const maxDiv = Math.max(...dividends);
  return (
    <div className={styles.postImgCalendarioDividendos}>
      <svg viewBox="0 0 200 120" width="200" height="120" fill="none" aria-hidden="true">
        <text x="100" y="12" fontSize="7" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle" letterSpacing="0.08em">INGRESOS POR DIVIDENDOS — MES A MES</text>
        {months.map((m, i) => {
          const x = 14 + i * 15.5;
          const h = Math.round((dividends[i] / maxDiv) * 65);
          const y = 100 - h;
          const isPeak = dividends[i] >= 200;
          return (
            <g key={m}>
              <rect x={x} y={y} width="11" height={h} rx="2" fill={isPeak ? 'var(--fv-ochre)' : 'rgba(154,107,31,0.25)'}/>
              <text x={x + 5.5} y={112} fontSize="5" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">{m}</text>
            </g>
          );
        })}
        <line x1="10" y1="100" x2="195" y2="100" stroke="var(--fv-ink-20)" strokeWidth="1"/>
        <text x="100" y="55" fontSize="6" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">280€</text>
        <text x="100" y="62" fontSize="5" fill="var(--fv-ink-30)" fontFamily="system-ui" textAnchor="middle">junio</text>
      </svg>
    </div>
  );
}

function ImgCapturaDividendo() {
  return (
    <div className={styles.postImgCapturaDividendo}>
      <svg viewBox="0 0 200 120" width="200" height="120" fill="none" aria-hidden="true">
        <text x="100" y="14" fontSize="7" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle" letterSpacing="0.08em">CAPTURA DE DIVIDENDO — IRPF</text>
        <rect x="14" y="34" width="46" height="40" rx="5" stroke="var(--fv-ochre)" strokeWidth="1.5" fill="var(--fv-ochre-ghost)"/>
        <text x="37" y="52" fontSize="7" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">COMPRA</text>
        <text x="37" y="64" fontSize="6" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">ex-date -1d</text>
        <path d="M60,54 L74,54" stroke="var(--fv-ink-30)" strokeWidth="1.5"/>
        <polygon points="74,49 84,54 74,59" fill="var(--fv-ink-30)"/>
        <circle cx="92" cy="44" r="9" fill="var(--fv-ochre)"/>
        <text x="92" y="47" fontSize="7" fill="#fff" fontFamily="system-ui" textAnchor="middle">D</text>
        <text x="92" y="62" fontSize="5.5" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">dividendo</text>
        <rect x="104" y="34" width="46" height="40" rx="5" stroke="var(--fv-ink-20)" strokeWidth="1" fill="none"/>
        <text x="127" y="52" fontSize="7" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">VENTA</text>
        <text x="127" y="64" fontSize="6" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">ex-date +1d</text>
        <rect x="150" y="80" width="44" height="22" rx="4" stroke="var(--fv-ochre)" strokeWidth="1.5" fill="var(--fv-ochre-ghost)"/>
        <text x="172" y="90" fontSize="6" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">Hacienda</text>
        <text x="172" y="98" fontSize="7" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">-7,13 EUR</text>
        <text x="100" y="114" fontSize="5.5" fill="var(--fv-ink-30)" fontFamily="system-ui" textAnchor="middle">0 EUR en bolsillo, impuesto seguro</text>
      </svg>
    </div>
  );
}

function ImgCompensarPerdidas() {
  return (
    <div className={styles.postImgCompensarPerdidas}>
      <svg viewBox="0 0 200 120" width="200" height="120" fill="none" aria-hidden="true">
        <text x="100" y="14" fontSize="8" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle" letterSpacing="0.08em">COMPENSACIÓN BASE DEL AHORRO</text>
        <rect x="15" y="30" width="75" height="70" rx="6" stroke="var(--fv-ink-20)" strokeWidth="1" fill="none"/>
        <text x="52" y="46" fontSize="7" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">Bloque A</text>
        <text x="52" y="58" fontSize="6" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">Ventas</text>
        <text x="52" y="72" fontSize="8" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">−2.000 €</text>
        <text x="52" y="86" fontSize="6" fill="var(--fv-ink-30)" fontFamily="system-ui" textAnchor="middle">saldo negativo</text>
        <rect x="110" y="30" width="75" height="70" rx="6" stroke="var(--fv-ochre)" strokeWidth="1.5" fill="var(--fv-ochre-ghost)"/>
        <text x="147" y="46" fontSize="7" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">Bloque B</text>
        <text x="147" y="58" fontSize="6" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">Dividendos</text>
        <text x="147" y="72" fontSize="8" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">+2.500 €</text>
        <text x="147" y="86" fontSize="6" fill="var(--fv-ink-30)" fontFamily="system-ui" textAnchor="middle">25% tope = 625 €</text>
        <line x1="90" y1="65" x2="110" y2="65" stroke="var(--fv-ochre)" strokeWidth="1.5" strokeDasharray="3 2" markerEnd="url(#arrow)"/>
        <defs>
          <marker id="arrow" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
            <path d="M0,0 L6,3 L0,6" fill="var(--fv-ochre)"/>
          </marker>
        </defs>
        <text x="100" y="110" fontSize="6" fill="var(--fv-ink-30)" fontFamily="system-ui" textAnchor="middle">Resultado: tributas por 1.875 €</text>
      </svg>
    </div>
  );
}

function ImgCriptomonedas() {
  return (
    <div className={styles.postImgCriptomonedas}>
      <svg viewBox="0 0 200 120" width="200" height="120" fill="none" aria-hidden="true">
        <text x="100" y="14" fontSize="7" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle" letterSpacing="0.08em">CRIPTOMONEDAS — BASE DEL AHORRO</text>
        {/* BTC block */}
        <rect x="12" y="28" width="50" height="72" rx="6" stroke="var(--fv-ochre)" strokeWidth="1.5" fill="var(--fv-ochre-ghost)"/>
        <text x="37" y="44" fontSize="7" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">BTC</text>
        <text x="37" y="58" fontSize="6" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">Compra</text>
        <text x="37" y="72" fontSize="8" fill="var(--fv-ink)" fontFamily="system-ui" textAnchor="middle">20K€</text>
        <text x="37" y="86" fontSize="5" fill="var(--fv-ink-30)" fontFamily="system-ui" textAnchor="middle">enero</text>
        {/* Arrow */}
        <line x1="62" y1="64" x2="78" y2="64" stroke="var(--fv-ochre)" strokeWidth="1.5"/>
        {/* Sale block */}
        <rect x="78" y="28" width="50" height="72" rx="6" stroke="var(--fv-ink-20)" strokeWidth="1" fill="none"/>
        <text x="103" y="44" fontSize="7" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">Venta</text>
        <text x="103" y="58" fontSize="6" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">octubre</text>
        <text x="103" y="72" fontSize="8" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">45K€</text>
        <text x="103" y="86" fontSize="5" fill="var(--fv-ink-30)" fontFamily="system-ui" textAnchor="middle">+25K€</text>
        {/* Tax block */}
        <rect x="138" y="40" width="50" height="60" rx="6" stroke="var(--fv-ochre)" strokeWidth="1.5" fill="var(--fv-ochre-ghost)"/>
        <text x="163" y="56" fontSize="7" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">IRPF</text>
        <text x="163" y="70" fontSize="6" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">ahorro</text>
        <text x="163" y="84" fontSize="9" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">19-30%</text>
      </svg>
    </div>
  );
}

function ImgCuandoVender() {
  return (
    <div className={styles.postImgCuandoVender}>
      <svg viewBox="0 0 200 120" width="200" height="120" fill="none" aria-hidden="true">
        <text x="100" y="13" fontSize="7" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle" letterSpacing="0.08em">GESTIÓN DE CARTERA · CUÁNDO SALIR</text>
        <rect x="46" y="18" width="108" height="16" rx="8" fill="var(--fv-ochre-ghost)" stroke="var(--fv-ochre)" strokeWidth="1.5"/>
        <text x="100" y="29" fontSize="7" fill="var(--fv-ink)" fontFamily="system-ui" textAnchor="middle">VENDER NO ES FRACASAR</text>
        {/* Exit door */}
        <rect x="18" y="44" width="36" height="58" rx="4" stroke="var(--fv-ochre)" strokeWidth="1.8" fill="var(--fv-ochre-ghost)"/>
        <rect x="46" y="62" width="5" height="10" rx="2" fill="var(--fv-ochre)"/>
        <path d="M36 70 L52 70 M52 70 L46 64 M52 70 L46 76" stroke="var(--fv-ochre)" strokeWidth="1.5" fill="none"/>
        <text x="36" y="112" fontSize="6" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">VENDER</text>
        {/* Reinvestment staircase */}
        <rect x="112" y="94" width="12" height="14" fill="var(--fv-ochre-ghost)" stroke="var(--fv-ochre)" strokeWidth="1"/>
        <rect x="128" y="88" width="12" height="20" fill="var(--fv-ochre-ghost)" stroke="var(--fv-ochre)" strokeWidth="1"/>
        <rect x="144" y="80" width="12" height="28" fill="var(--fv-ink-40)"/>
        <rect x="160" y="70" width="12" height="38" fill="var(--fv-ochre)" rx="1.5"/>
        <text x="140" y="113" fontSize="6" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">REINVERTIR</text>
        {/* coin flowing from door to market */}
        <circle cx="80" cy="78" r="6" fill="var(--fv-ochre)"/>
        <text x="80" y="81" fontSize="6" fill="var(--fv-paper,#fff8ec)" fontFamily="system-ui" textAnchor="middle">€</text>
        <path d="M66 90 C76 100, 94 100, 104 92" stroke="var(--fv-ink-30)" strokeWidth="1.2" strokeDasharray="3 2"/>
      </svg>
    </div>
  );
}

function ImgCuentasConjuntas() {
  return (
    <div className={styles.postImgCuentasConjuntas}>
      <svg viewBox="0 0 200 120" width="200" height="120" fill="none" aria-hidden="true">
        <text x="100" y="15" fontSize="8" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle" letterSpacing="0.08em">TITULARIDAD 50 / 50</text>
        {/* Shared account block splitting into two owners */}
        <rect x="66" y="26" width="68" height="20" rx="4" stroke="var(--fv-ink-30)" strokeWidth="1.5" fill="none"/>
        <text x="100" y="40" fontSize="8" fill="var(--fv-ink)" fontFamily="system-ui" textAnchor="middle">CUENTA</text>
        {/* Split paths */}
        <path d="M84,46 L84,60 L52,60 L52,72" stroke="var(--fv-ochre)" strokeWidth="1.5" fill="none"/>
        <path d="M116,46 L116,60 L148,60 L148,72" stroke="var(--fv-ink-40)" strokeWidth="1.5" fill="none"/>
        {/* Owner A */}
        <circle cx="52" cy="86" r="14" stroke="var(--fv-ochre)" strokeWidth="1.5" fill="var(--fv-ochre-ghost)"/>
        <text x="52" y="90" fontSize="10" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">50%</text>
        {/* Owner B */}
        <circle cx="148" cy="86" r="14" stroke="var(--fv-ink-30)" strokeWidth="1.5" fill="none"/>
        <text x="148" y="90" fontSize="10" fill="var(--fv-ink)" fontFamily="system-ui" textAnchor="middle">50%</text>
        <text x="100" y="112" fontSize="7" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">IRPF · art. 11.3</text>
      </svg>
    </div>
  );
}

function ImgCuentasRemuneradas() {
  return (
    <div className={styles.postImgCuentasRemuneradas}>
      <svg viewBox="0 0 200 120" width="200" height="120" fill="none" aria-hidden="true">
        <text x="100" y="14" fontSize="8" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle" letterSpacing="0.08em">INTERÉS 3 % · RETENCIÓN 19 %</text>
        {/* Importe bruto */}
        <circle cx="60" cy="62" r="20" stroke="var(--fv-ink-30)" strokeWidth="1.5" fill="none"/>
        <text x="60" y="67" fontSize="14" fill="var(--fv-ink)" fontFamily="system-ui" textAnchor="middle">€</text>
        <text x="60" y="92" fontSize="7" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">bruto</text>
        {/* Split */}
        <path d="M80,60 L120,44 L120,74" stroke="var(--fv-ochre)" strokeWidth="1.5" fill="none"/>
        <polygon points="120,74 113,62 127,62" fill="var(--fv-ochre)"/>
        {/* Hacienda 19% */}
        <rect x="120" y="22" width="56" height="20" rx="4" stroke="var(--fv-ochre)" strokeWidth="1.5" fill="var(--fv-ochre-ghost)"/>
        <text x="148" y="36" fontSize="8" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">19 %</text>
        {/* Neto */}
        <rect x="120" y="74" width="56" height="20" rx="4" stroke="var(--fv-ink-30)" strokeWidth="1.5" fill="none"/>
        <text x="148" y="88" fontSize="7" fill="var(--fv-ink)" fontFamily="system-ui" textAnchor="middle">2,43 %</text>
        <text x="100" y="112" fontSize="7" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">el banco retiene · Hacienda cobra después</text>
      </svg>
    </div>
  );
}

function ImgDerechosSuscripcion() {
  return (
    <div className={styles.postImgDerechosSuscripcion}>
      <svg viewBox="0 0 200 120" width="200" height="120" fill="none" aria-hidden="true">
        <text x="100" y="12" fontSize="7" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle" letterSpacing="0.08em">DSP — 3 OPCIONES, 3 FISCALIDADES</text>
        {/* Shareholder box */}
        <rect x="5" y="28" width="40" height="50" rx="4" stroke="var(--fv-ochre)" strokeWidth="1.5" fill="var(--fv-ochre-ghost)"/>
        <text x="25" y="46" fontSize="6" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">Tienes</text>
        <text x="25" y="58" fontSize="6" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">100 DSP</text>
        <text x="25" y="72" fontSize="5" fill="var(--fv-ink-30)" fontFamily="system-ui" textAnchor="middle">de Iberdrola</text>
        {/* Arrow to subscribe */}
        <line x1="45" y1="38" x2="60" y2="32" stroke="var(--fv-ochre)" strokeWidth="1"/>
        {/* Subscribe option */}
        <rect x="60" y="20" width="48" height="30" rx="5" stroke="var(--fv-ochre)" strokeWidth="1.5" fill="var(--fv-ochre-ghost)"/>
        <text x="84" y="33" fontSize="6" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">Suscribir</text>
        <text x="84" y="44" fontSize="5" fill="var(--fv-ink-30)" fontFamily="system-ui" textAnchor="middle">0€ ahora</text>
        {/* Arrow to sell market */}
        <line x1="45" y1="53" x2="60" y2="53" stroke="var(--fv-ink-40)" strokeWidth="1"/>
        {/* Sell market option */}
        <rect x="60" y="45" width="48" height="30" rx="5" stroke="var(--fv-ink-20)" strokeWidth="1" fill="none"/>
        <text x="84" y="58" fontSize="6" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">Vender</text>
        <text x="84" y="69" fontSize="5" fill="var(--fv-ink-30)" fontFamily="system-ui" textAnchor="middle">gan. patrim.</text>
        {/* Arrow to sell company */}
        <line x1="45" y1="68" x2="60" y2="74" stroke="var(--fv-ink-40)" strokeWidth="1"/>
        {/* Sell company option */}
        <rect x="60" y="70" width="48" height="30" rx="5" stroke="var(--fv-ink-20)" strokeWidth="1" fill="none"/>
        <text x="84" y="83" fontSize="6" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">Empresa</text>
        <text x="84" y="94" fontSize="5" fill="var(--fv-ink-30)" fontFamily="system-ui" textAnchor="middle">rend. capit.</text>
        {/* Result labels */}
        <rect x="118" y="20" width="72" height="24" rx="4" fill="var(--fv-ochre-ghost)"/>
        <text x="154" y="36" fontSize="5" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">Diferido → plusvalía al vender</text>
        <rect x="118" y="50" width="72" height="18" rx="4" fill="rgba(31,27,22,0.04)"/>
        <text x="154" y="63" fontSize="5" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">19% retención · Bloque A</text>
        <rect x="118" y="76" width="72" height="18" rx="4" fill="rgba(31,27,22,0.04)"/>
        <text x="154" y="89" fontSize="5" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">19% retención · Bloque B</text>
        {/* Bottom note */}
        <text x="100" y="108" fontSize="5" fill="var(--fv-ink-30)" fontFamily="system-ui" textAnchor="middle">Misma cuantía, distinto bloque → distinto ahorro fiscal</text>
      </svg>
    </div>
  );
}

function ImgDgi() {
  return (
    <div className={styles.postImgDgi}>
      <svg viewBox="0 0 200 120" width="200" height="120" fill="none" aria-hidden="true">
        {([20,40,60,80,100,120,140,160,180]).map((x, i) => {
          const heights = [20,32,44,38,56,70,62,84,96];
          return (
            <rect key={x} x={x - 12} y={110 - heights[i]} width="20" height={heights[i]}
              fill={i === 8 ? 'var(--fv-ochre)' : 'rgba(154,107,31,0.25)'} rx="3"/>
          );
        })}
        <polyline
          points="8,90 28,78 48,66 68,72 88,54 108,40 128,48 148,26 168,14 188,4"
          stroke="var(--fv-ochre)" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round"
        />
      </svg>
    </div>
  );
}

function ImgDividendoMensual() {
  return (
    <div className={styles.postImgDividendoMensual}>
      <svg viewBox="0 0 200 120" width="200" height="120" fill="none" aria-hidden="true">
        <text x="100" y="14" fontSize="7" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle" letterSpacing="0.08em">12 PAGOS AL AÑO</text>
        {([12,27,42,57,72,87,102,117,132,147,162,177]).map((x, i) => {
          const heights = [18,20,19,22,21,24,23,26,25,28,27,30];
          return (
            <rect key={x} x={x - 4} y={104 - heights[i]} width="9" height={heights[i]}
              fill={i === 11 ? 'var(--fv-ochre)' : 'rgba(154,107,31,0.25)'} rx="2"/>
          );
        })}
        <text x="100" y="117" fontSize="6" fill="var(--fv-ink-30)" fontFamily="system-ui" textAnchor="middle">enero · febrero · ... · diciembre</text>
      </svg>
    </div>
  );
}

function ImgDividendoVsAlquiler() {
  return (
    <div className={styles.postImgDividendoVsAlquiler}>
      <svg viewBox="0 0 200 120" width="200" height="120" fill="none" aria-hidden="true">
        <text x="100" y="14" fontSize="7" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle" letterSpacing="0.08em">MISMO EURO · DISTINTA BASE</text>
        {/* Dividendo column */}
        <rect x="20" y="28" width="62" height="74" rx="6" stroke="var(--fv-ochre)" strokeWidth="1.5" fill="var(--fv-ochre-ghost)"/>
        <text x="51" y="46" fontSize="7" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">DIVIDENDO</text>
        <text x="51" y="60" fontSize="6" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">Base ahorro</text>
        <circle cx="51" cy="82" r="9" fill="var(--fv-ochre)"/>
        <text x="51" y="86" fontSize="9" fill="#fff" fontFamily="system-ui" textAnchor="middle">€</text>
        <text x="51" y="100" fontSize="7" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">19-21%</text>
        {/* Alquiler column */}
        <rect x="118" y="28" width="62" height="74" rx="6" stroke="var(--fv-ink-20)" strokeWidth="1" fill="none"/>
        <text x="149" y="46" fontSize="7" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">ALQUILER</text>
        <text x="149" y="60" fontSize="6" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">Renta general</text>
        <circle cx="149" cy="82" r="9" fill="var(--fv-ink-20)"/>
        <text x="149" y="86" fontSize="9" fill="var(--fv-ink)" fontFamily="system-ui" textAnchor="middle">€</text>
        <text x="149" y="100" fontSize="7" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">30-37%</text>
        {/* Not equal sign between */}
        <text x="100" y="70" fontSize="14" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">≠</text>
      </svg>
    </div>
  );
}

function ImgDividendosExtranjeros() {
  return (
    <div className={styles.postImgDividendosExtranjeros}>
      <svg viewBox="0 0 200 120" width="200" height="120" fill="none" aria-hidden="true">
        <text x="100" y="14" fontSize="7" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle" letterSpacing="0.08em">DIVIDENDO BRUTO vs NETO</text>
        {/* Gross dividend bar */}
        <rect x="20" y="40" width="36" height="50" rx="4" stroke="var(--fv-ochre)" strokeWidth="1.5" fill="var(--fv-ochre-ghost)"/>
        <text x="38" y="58" fontSize="7" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">Bruto</text>
        <text x="38" y="72" fontSize="9" fill="var(--fv-ink)" fontFamily="system-ui" textAnchor="middle">100€</text>
        {/* Retention arrow */}
        <line x1="56" y1="65" x2="72" y2="65" stroke="var(--fv-ink-30)" strokeWidth="1" strokeDasharray="3 2"/>
        <text x="64" y="60" fontSize="6" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">30%</text>
        {/* US tax */}
        <rect x="72" y="50" width="36" height="40" rx="4" stroke="var(--fv-ink-20)" strokeWidth="1" fill="none"/>
        <text x="90" y="66" fontSize="7" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">EE.UU.</text>
        <text x="90" y="80" fontSize="8" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">−30€</text>
        {/* Arrow to Spain */}
        <line x1="108" y1="65" x2="124" y2="65" stroke="var(--fv-ochre)" strokeWidth="1.5"/>
        {/* Spain tax */}
        <rect x="124" y="40" width="36" height="50" rx="4" stroke="var(--fv-ochre)" strokeWidth="1.5" fill="var(--fv-ochre-ghost)"/>
        <text x="142" y="58" fontSize="7" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">España</text>
        <text x="142" y="72" fontSize="9" fill="var(--fv-ink)" fontFamily="system-ui" textAnchor="middle">100€</text>
        <text x="142" y="82" fontSize="6" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">base ahorro</text>
        {/* Bottom annotation */}
        <text x="100" y="108" fontSize="6" fill="var(--fv-ink-30)" fontFamily="system-ui" textAnchor="middle">Sin W-8BEN: pagas 30€ + 19€ = 49€ por 100€ de dividendo</text>
      </svg>
    </div>
  );
}

function ImgDividendosHaciendaForal() {
  return (
    <div className={styles.postImgDividendosHaciendaForal}>
      <svg viewBox="0 0 200 120" width="200" height="120" fill="none" aria-hidden="true">
        <text x="100" y="14" fontSize="7" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle" letterSpacing="0.08em">HACIENDA FORAL VS COMÚN</text>
        {/* Foral box */}
        <rect x="20" y="30" width="70" height="65" rx="6" stroke="var(--fv-ochre)" strokeWidth="1.5" fill="var(--fv-ochre-ghost)"/>
        <text x="55" y="50" fontSize="7" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">FORAL</text>
        <text x="55" y="65" fontSize="6" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">Navarra</text>
        <text x="55" y="80" fontSize="10" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">15%</text>
        {/* Common regime box */}
        <rect x="110" y="30" width="70" height="65" rx="6" stroke="var(--fv-ink-20)" strokeWidth="1" fill="none"/>
        <text x="145" y="50" fontSize="7" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">COMÚN</text>
        <text x="145" y="65" fontSize="6" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">España</text>
        <text x="145" y="80" fontSize="10" fill="var(--fv-ink)" fontFamily="system-ui" textAnchor="middle">19%</text>
        {/* vs text */}
        <text x="100" y="110" fontSize="6" fill="var(--fv-ink-30)" fontFamily="system-ui" textAnchor="middle">primer tramo base ahorro</text>
      </svg>
    </div>
  );
}

function ImgDividendosInflacion() {
  return (
    <div className={styles.postImgDividendosInflacion}>
      <svg viewBox="0 0 200 120" width="200" height="120" fill="none" aria-hidden="true">
        <text x="100" y="13" fontSize="6.5" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle" letterSpacing="0.06em">NOMINAL vs REAL</text>
        {/* Nominal cluster: bars grow up (ochre) */}
        <rect x="22" y="73" width="14" height="22" rx="2" fill="rgba(154,107,31,0.3)"/>
        <rect x="40" y="57" width="14" height="38" rx="2" fill="rgba(154,107,31,0.45)"/>
        <rect x="58" y="41" width="14" height="54" rx="2" fill="var(--fv-ochre)"/>
        <text x="42" y="106" fontSize="6.5" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">NOMINAL ↑</text>
        {/* Real cluster: bars shrink (faded ink) */}
        <rect x="122" y="49" width="14" height="46" rx="2" fill="rgba(31,27,22,0.18)"/>
        <rect x="140" y="63" width="14" height="32" rx="2" fill="rgba(31,27,22,0.14)"/>
        <rect x="158" y="77" width="14" height="18" rx="2" fill="rgba(31,27,22,0.10)"/>
        <text x="140" y="106" fontSize="6.5" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">REAL ↓</text>
        {/* Diverging diagonal: nominal up, real down */}
        <line x1="72" y1="44" x2="118" y2="76" stroke="var(--fv-ochre)" strokeWidth="1.5" strokeDasharray="4 3"/>
        <text x="100" y="114" fontSize="5.5" fill="var(--fv-ink-30)" fontFamily="system-ui" textAnchor="middle">cobras más, compras menos</text>
      </svg>
    </div>
  );
}

function ImgDividendosVsEtf() {
  // Side-by-side: bar chart (stocks) vs growing plant curve (ETF acc)
  const buyFlows = [30, 35, 42, 38, 50, 45, 55, 60];
  const etfCurve = [30, 36, 43, 51, 60, 70, 82, 95];
  const maxY = 110;
  return (
    <div className={styles.postImgDividendosVsEtf}>
      <svg viewBox="0 0 200 120" width="200" height="120" fill="none" aria-hidden="true">
        <text x="100" y="12" fontSize="6.5" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle" letterSpacing="0.06em">LASTRE FISCAL ANUAL vs DIFERIMIENTO</text>
        {/* Left bars = buy/sell leak every year */}
        <text x="52" y="24" fontSize="6" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">Acciones</text>
        {buyFlows.map((h, i) => {
          const x = 14 + i * 10;
          return (
            <rect key={`b${i}`} x={x} y={maxY - h * 1.2} width="7" height={h * 1.2}
              fill={i === buyFlows.length - 1 ? 'var(--fv-ochre)' : 'rgba(154,107,31,0.25)'} rx="1.5"/>
          );
        })}
        {/* Tax leak arrows */}
        <line x1="100" y1="60" x2="100" y2="58" stroke="var(--fv-ink-30)" strokeWidth="0.5"/>
        <text x="100" y="72" fontSize="5.5" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle" fontWeight="600">−19%/año</text>
        {/* Right curve = ETF compounding growth */}
        <text x="148" y="24" fontSize="6" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">ETF Acc</text>
        <polyline
          points={etfCurve.map((h, i) => `${110 + i * 11},${maxY - h * 1.0}`).join(' ')}
          stroke="var(--fv-ochre)" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round"
        />
        <circle cx="198" cy={maxY - etfCurve[etfCurve.length - 1] * 1.0} r="3" fill="var(--fv-ochre)"/>
        {/* Dashed separator */}
        <line x1="105" y1="28" x2="105" y2="112" stroke="var(--fv-ink-15)" strokeWidth="0.8" strokeDasharray="2 2"/>
        {/* Bottom annotation */}
        <text x="100" y="118" fontSize="5" fill="var(--fv-ink-30)" fontFamily="system-ui" textAnchor="middle">20 años · 50K€ inicial + 500€/mes · 7% bruto</text>
      </svg>
    </div>
  );
}

function ImgFiscalidadOpciones() {
  return (
    <div className={styles.postImgFiscalidadOpciones}>
      <svg viewBox="0 0 200 120" width="200" height="120" fill="none" aria-hidden="true">
        <text x="100" y="13" fontSize="7" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle" letterSpacing="0.08em">PUT VENDIDA — 3 DESENLACES</text>
        {/* Prima coin at origin */}
        <circle cx="30" cy="62" r="16" fill="var(--fv-ochre-ghost)" stroke="var(--fv-ochre)" strokeWidth="1.5"/>
        <text x="30" y="60" fontSize="7" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">prima</text>
        <text x="30" y="70" fontSize="7" fill="var(--fv-ink)" fontFamily="system-ui" textAnchor="middle">+45 €</text>
        {/* Branch lines */}
        <path d="M46 56 C70 40, 84 34, 104 32" stroke="var(--fv-ink-30)" strokeWidth="1.2" fill="none"/>
        <path d="M46 62 L104 62" stroke="var(--fv-ink-30)" strokeWidth="1.2"/>
        <path d="M46 68 C70 84, 84 90, 104 92" stroke="var(--fv-ochre)" strokeWidth="1.5" fill="none"/>
        {/* Outcome boxes */}
        <rect x="106" y="20" width="82" height="24" rx="5" stroke="var(--fv-ink-20)" strokeWidth="1" fill="none"/>
        <text x="147" y="30" fontSize="6" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">Expira sin valor</text>
        <text x="147" y="39" fontSize="6" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">ganancia: prima</text>
        <rect x="106" y="50" width="82" height="24" rx="5" stroke="var(--fv-ink-20)" strokeWidth="1" fill="none"/>
        <text x="147" y="60" fontSize="6" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">Recompra</text>
        <text x="147" y="69" fontSize="6" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">± diferencia</text>
        <rect x="106" y="80" width="82" height="24" rx="5" stroke="var(--fv-ochre)" strokeWidth="1.5" fill="var(--fv-ochre-ghost)"/>
        <text x="147" y="90" fontSize="6" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">Ejercicio</text>
        <text x="147" y="99" fontSize="6" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">acciones al strike</text>
        <text x="100" y="115" fontSize="5.5" fill="var(--fv-ink-30)" fontFamily="system-ui" textAnchor="middle">Ganancia patrimonial · base del ahorro · sin retención</text>
      </svg>
    </div>
  );
}

function ImgFondosVsEtf() {
  return (
    <div className={styles.postImgFondosVsEtf}>
      <svg viewBox="0 0 200 120" width="200" height="120" fill="none" aria-hidden="true">
        <text x="100" y="14" fontSize="7" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle" letterSpacing="0.08em">FONDO vs ETF — TRASPASO</text>
        {/* Fund box */}
        <rect x="15" y="30" width="70" height="70" rx="6" stroke="var(--fv-ochre)" strokeWidth="1.5" fill="var(--fv-ochre-ghost)"/>
        <text x="50" y="48" fontSize="7" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">Fondo</text>
        <text x="50" y="62" fontSize="6" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">Traspaso</text>
        <text x="50" y="76" fontSize="8" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">0 €</text>
        <text x="50" y="88" fontSize="5" fill="var(--fv-ink-30)" fontFamily="system-ui" textAnchor="middle">sin tributar</text>
        {/* Arrow */}
        <line x1="85" y1="65" x2="105" y2="65" stroke="var(--fv-ink-30)" strokeWidth="1" strokeDasharray="3 2"/>
        {/* ETF box */}
        <rect x="115" y="30" width="70" height="70" rx="6" stroke="var(--fv-ink-20)" strokeWidth="1" fill="none"/>
        <text x="150" y="48" fontSize="7" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">ETF</text>
        <text x="150" y="62" fontSize="6" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">Venta</text>
        <text x="150" y="76" fontSize="8" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">21%</text>
        <text x="150" y="88" fontSize="5" fill="var(--fv-ink-30)" fontFamily="system-ui" textAnchor="middle">tributa plusvalía</text>
      </svg>
    </div>
  );
}

function ImgGastosDeducibles() {
  return (
    <div className={styles.postImgGastosDeducibles}>
      <svg viewBox="0 0 200 120" width="200" height="120" fill="none" aria-hidden="true">
        <text x="100" y="12" fontSize="7" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle" letterSpacing="0.08em">GASTOS DEDUCIBLES — BASE DEL AHORRO</text>
        {/* Income box */}
        <rect x="12" y="28" width="50" height="60" rx="6" stroke="var(--fv-ochre)" strokeWidth="1.5" fill="var(--fv-ochre-ghost)"/>
        <text x="37" y="46" fontSize="7" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">Bruto</text>
        <text x="37" y="60" fontSize="8" fill="var(--fv-ink)" fontFamily="system-ui" textAnchor="middle">3.000€</text>
        <text x="37" y="74" fontSize="5" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">dividendos</text>
        {/* Arrow with expense */}
        <line x1="62" y1="58" x2="82" y2="58" stroke="var(--fv-ink-30)" strokeWidth="1.5"/>
        <text x="72" y="52" fontSize="6" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">−50€</text>
        <text x="72" y="68" fontSize="5" fill="var(--fv-ink-30)" fontFamily="system-ui" textAnchor="middle">custodia</text>
        {/* Net box */}
        <rect x="88" y="28" width="50" height="60" rx="6" stroke="var(--fv-ink-20)" strokeWidth="1" fill="none"/>
        <text x="113" y="46" fontSize="7" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">Neto</text>
        <text x="113" y="60" fontSize="8" fill="var(--fv-ink)" fontFamily="system-ui" textAnchor="middle">2.950€</text>
        <text x="113" y="74" fontSize="5" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">a declarar</text>
        {/* Tax box */}
        <rect x="148" y="38" width="40" height="50" rx="4" stroke="var(--fv-ochre)" strokeWidth="1.5" fill="var(--fv-ochre-ghost)"/>
        <text x="168" y="54" fontSize="6" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">IRPF</text>
        <text x="168" y="66" fontSize="8" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">19%</text>
        <text x="168" y="78" fontSize="5" fill="var(--fv-ink-30)" fontFamily="system-ui" textAnchor="middle">sobre neto</text>
        {/* Bottom annotation */}
        <text x="100" y="108" fontSize="5.5" fill="var(--fv-ink-30)" fontFamily="system-ui" textAnchor="middle">Gastos de administración y depósito restan del bruto</text>
      </svg>
    </div>
  );
}

function ImgHeredarAcciones() {
  return (
    <div className={styles.postImgHeredarAcciones}>
      <svg viewBox="0 0 200 120" width="200" height="120" fill="none" aria-hidden="true">
        {/* stack of share certificates passing between two generations */}
        <circle cx="40" cy="40" r="16" stroke="var(--fv-ink-40)" strokeWidth="2"/>
        <path d="M24 74 q16 -14 32 0" stroke="var(--fv-ink-40)" strokeWidth="2" strokeLinecap="round"/>
        <circle cx="160" cy="40" r="16" stroke="var(--fv-ochre)" strokeWidth="2"/>
        <path d="M144 74 q16 -14 32 0" stroke="var(--fv-ochre)" strokeWidth="2" strokeLinecap="round"/>
        {/* certificates */}
        <rect x="82" y="30" width="36" height="26" rx="3" fill="var(--fv-ochre-ghost)" stroke="var(--fv-ochre)" strokeWidth="1.5"/>
        <rect x="78" y="26" width="36" height="26" rx="3" fill="#fff" stroke="var(--fv-ink-30)" strokeWidth="1.5"/>
        <line x1="84" y1="34" x2="106" y2="34" stroke="var(--fv-ink-30)" strokeWidth="1.5"/>
        <line x1="84" y1="40" x2="100" y2="40" stroke="var(--fv-ink-30)" strokeWidth="1.5"/>
        {/* arrow of transfer */}
        <path d="M62 44 H74 M126 44 H138" stroke="var(--fv-ochre)" strokeWidth="2" strokeLinecap="round"/>
        <path d="M134 40 l6 4 -6 4" stroke="var(--fv-ochre)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" fill="none"/>
        {/* erased gain: struck-through old cost */}
        <text x="100" y="98" fontSize="10" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">IRPF ganancia: 0 €</text>
        <text x="100" y="112" fontSize="8" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">plusvalía del muerto</text>
      </svg>
    </div>
  );
}

function ImgImpuestoPatrimonio() {
  return (
    <div className={styles.postImgImpuestoPatrimonio}>
      <svg viewBox="0 0 200 120" width="200" height="120" fill="none" aria-hidden="true">
        <text x="100" y="14" fontSize="7" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle" letterSpacing="0.08em">IMPUESTO PATRIMONIO — MODELO 714</text>
        {/* 700K exento */}
        <rect x="10" y="28" width="80" height="70" rx="6" stroke="var(--fv-ink-20)" strokeWidth="1" fill="none"/>
        <text x="50" y="46" fontSize="7" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">Exento</text>
        <text x="50" y="60" fontSize="8" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">700.000€</text>
        <text x="50" y="74" fontSize="5" fill="var(--fv-ink-30)" fontFamily="system-ui" textAnchor="middle">mínimo</text>
        {/* Flecha a cartera */}
        <line x1="90" y1="63" x2="108" y2="63" stroke="var(--fv-ochre)" strokeWidth="1.5"/>
        <polygon points="106,59 112,63 106,67" fill="var(--fv-ochre)"/>
        {/* Cartera invertida */}
        <rect x="112" y="28" width="78" height="70" rx="6" stroke="var(--fv-ochre)" strokeWidth="1.5" fill="var(--fv-ochre-ghost)"/>
        <text x="151" y="46" fontSize="7" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">Cartera</text>
        <text x="151" y="60" fontSize="8" fill="var(--fv-ink)" fontFamily="system-ui" textAnchor="middle">1.000.000€</text>
        <text x="151" y="74" fontSize="5" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">paga IP</text>
        {/* Flecha de salida */}
        <line x1="151" y1="98" x2="151" y2="108" stroke="var(--fv-ochre)" strokeWidth="1" markerEnd="url(#ipArrow)"/>
        <text x="165" y="108" fontSize="6" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">tipo 0,2-3,5%</text>
        <defs>
          <marker id="ipArrow" markerWidth="6" markerHeight="6" refX="3" refY="5" orient="auto">
            <path d="M0,0 L6,3 L0,6" fill="var(--fv-ochre)"/>
          </marker>
        </defs>
      </svg>
    </div>
  );
}

function ImgIrpf() {
  type IrpfRow = { label: string; value: string; y: number };
  const rows: IrpfRow[] = [
    { label: 'Casilla 27',  value: '1.529,64 €',  y: 44 },
    { label: 'Casilla 29',  value: '5.301,02 €',  y: 60 },
    { label: 'Casilla 332', value: '297,40 €',    y: 76 },
    { label: 'Casilla 337', value: '-2.155,11 €', y: 92 },
  ];
  return (
    <div className={styles.postImgIrpf}>
      <svg viewBox="0 0 180 120" width="180" height="120" fill="none" aria-hidden="true">
        <rect x="20" y="10" width="140" height="100" rx="8" stroke="var(--fv-ink-30)" strokeWidth="1.5"/>
        <line x1="20" y1="32" x2="160" y2="32" stroke="var(--fv-ink-15)" strokeWidth="1"/>
        {rows.map(({ label, value, y }) => (
          <g key={label}>
            <text x="30" y={y} fontSize="9" fill="var(--fv-ink-60)" fontFamily="system-ui">{label}</text>
            <text x="130" y={y} fontSize="9" fill="var(--fv-ink)" fontFamily="system-ui" textAnchor="end">{value}</text>
          </g>
        ))}
        <rect x="28" y="18" width="40" height="8" rx="2" fill="var(--fv-ochre-ghost)"/>
        <text x="48" y="25" fontSize="7" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">IRPF 2024</text>
      </svg>
    </div>
  );
}

function ImgMejoresEtfs() {
  return (
    <div className={styles.postImgMejoresEtfs}>
      <svg viewBox="0 0 200 120" width="200" height="120" fill="none" aria-hidden="true">
        <text x="100" y="14" fontSize="7" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle" letterSpacing="0.08em">MEJORES ETFs DE DIVIDENDOS 2026</text>
        {/* ETF cards */}
        <rect x="10" y="26" width="85" height="80" rx="6" stroke="var(--fv-ochre)" strokeWidth="1.5" fill="var(--fv-ochre-ghost)"/>
        <text x="52" y="44" fontSize="7" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">VHYL</text>
        <text x="52" y="56" fontSize="6" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">Global</text>
        <text x="52" y="70" fontSize="8" fill="var(--fv-ink)" fontFamily="system-ui" textAnchor="middle">3,8%</text>
        <text x="52" y="82" fontSize="5" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">TER 0,29%</text>
        <text x="52" y="94" fontSize="5" fill="var(--fv-ink-30)" fontFamily="system-ui" textAnchor="middle">Distribución</text>
        {/* Second ETF card */}
        <rect x="105" y="26" width="85" height="80" rx="6" stroke="var(--fv-ink-20)" strokeWidth="1" fill="none"/>
        <text x="147" y="44" fontSize="7" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">IQQY</text>
        <text x="147" y="56" fontSize="6" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">Calidad</text>
        <text x="147" y="70" fontSize="8" fill="var(--fv-ink)" fontFamily="system-ui" textAnchor="middle">3,2%</text>
        <text x="147" y="82" fontSize="5" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">TER 0,28%</text>
        <text x="147" y="94" fontSize="5" fill="var(--fv-ink-30)" fontFamily="system-ui" textAnchor="middle">Acumulación</text>
        {/* Checkmark */}
        <circle cx="52" cy="108" r="5" fill="var(--fv-ochre-ghost)" stroke="var(--fv-ochre)" strokeWidth="1.5"/>
        <polyline points="49,108 51,110 55,106" stroke="var(--fv-ochre)" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round"/>
      </svg>
    </div>
  );
}

function ImgMetodoDgi() {
  return (
    <div className={styles.postImgMetodoDgi}>
      <svg viewBox="0 0 200 120" width="200" height="120" fill="none" aria-hidden="true">
        {/* Abstract growing path representing DGI */}
        <path d="M20,100 C40,80 60,60 80,50 C100,40 120,30 140,20 C160,10 180,5 190,10" stroke="var(--fv-ochre)" strokeWidth="2.5" fill="none" strokeLinecap="round"/>
        <circle cx="140" cy="20" r="4" fill="var(--fv-ochre)"/>
        <circle cx="80" cy="50" r="3" fill="rgba(154,107,31,0.5)"/>
        <circle cx="30" cy="90" r="3" fill="rgba(154,107,31,0.3)"/>
        <text x="100" y="115" fontSize="7" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle" letterSpacing="0.08em">CONSTRUIR CARTERA DGI</text>
      </svg>
    </div>
  );
}

function ImgModelo720() {
  return (
    <div className={styles.postImgModelo720}>
      <svg viewBox="0 0 200 120" width="200" height="120" fill="none" aria-hidden="true">
        <text x="100" y="14" fontSize="7" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle" letterSpacing="0.08em">MODELO 720 — 3 BLOQUES</text>
        <rect x="12" y="28" width="50" height="72" rx="6" stroke="var(--fv-ochre)" strokeWidth="1.5" fill="var(--fv-ochre-ghost)"/>
        <text x="37" y="44" fontSize="7" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">A</text>
        <text x="37" y="56" fontSize="6" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">Cuentas</text>
        <text x="37" y="70" fontSize="8" fill="var(--fv-ink)" fontFamily="system-ui" textAnchor="middle">50K€</text>
        <text x="37" y="82" fontSize="5" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">bancos</text>
        <rect x="75" y="28" width="50" height="72" rx="6" stroke="var(--fv-ink-20)" strokeWidth="1" fill="none"/>
        <text x="100" y="44" fontSize="7" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">B</text>
        <text x="100" y="56" fontSize="6" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">Valores</text>
        <text x="100" y="70" fontSize="8" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">50K€</text>
        <text x="100" y="82" fontSize="5" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">ETFs</text>
        <rect x="138" y="28" width="50" height="72" rx="6" stroke="var(--fv-ink-20)" strokeWidth="1" fill="none"/>
        <text x="163" y="44" fontSize="7" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">C</text>
        <text x="163" y="56" fontSize="6" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">Inmuebles</text>
        <text x="163" y="70" fontSize="8" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">50K€</text>
        <text x="163" y="82" fontSize="5" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">extranjero</text>
      </svg>
    </div>
  );
}

function ImgMudarteExtranjero() {
  return (
    <div className={styles.postImgMudarteExtranjero}>
      <svg viewBox="0 0 200 120" width="200" height="120" fill="none" aria-hidden="true">
        <text x="100" y="13" fontSize="7" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle" letterSpacing="0.08em">CAMBIO DE RESIDENCIA · IRPF → IRNR</text>
        {/* Left: Spain / IRPF portfolio */}
        <rect x="10" y="26" width="74" height="56" rx="4" stroke="var(--fv-ink-30)" strokeWidth="1.5" fill="none"/>
        <text x="47" y="40" fontSize="6" fill="var(--fv-ink)" fontFamily="system-ui" textAnchor="middle">ESPAÑA · IRPF</text>
        <rect x="18" y="60" width="12" height="16" fill="var(--fv-ochre-ghost)" stroke="var(--fv-ochre)" strokeWidth="1"/>
        <rect x="34" y="54" width="12" height="22" fill="var(--fv-ochre-ghost)" stroke="var(--fv-ochre)" strokeWidth="1"/>
        <rect x="50" y="48" width="12" height="28" fill="var(--fv-ochre)" rx="1.5"/>
        <rect x="66" y="44" width="12" height="32" fill="var(--fv-ochre)"/>
        {/* Arrow crossing to abroad */}
        <path d="M86 54 L114 54" stroke="var(--fv-ochre)" strokeWidth="1.8"/>
        <polygon points="114,48 128,54 114,60" fill="var(--fv-ochre)"/>
        <circle cx="107" cy="46" r="6" fill="var(--fv-paper,#fff8ec)" stroke="var(--fv-ochre)" strokeWidth="1.2"/>
        <text x="107" y="49" fontSize="7" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">19%</text>
        {/* Right: abroad / IRNR */}
        <rect x="128" y="26" width="62" height="56" rx="4" stroke="var(--fv-ink-30)" strokeWidth="1.5" fill="var(--fv-ochre-ghost)"/>
        <text x="159" y="40" fontSize="6" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">FUERA · IRNR</text>
        <circle cx="147" cy="64" r="8" fill="var(--fv-paper,#fff8ec)" stroke="var(--fv-ochre)" strokeWidth="1.2"/>
        <text x="147" y="67" fontSize="6" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">€</text>
        <circle cx="171" cy="64" r="8" fill="var(--fv-paper,#fff8ec)" stroke="var(--fv-ochre)" strokeWidth="1.2"/>
        <text x="171" y="67" fontSize="6" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">€</text>
        {/* 183 day divider */}
        <line x1="10" y1="100" x2="190" y2="100" stroke="var(--fv-ink-30)" strokeWidth="1" strokeDasharray="3 3"/>
        <text x="100" y="114" fontSize="6" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">183 DÍAS · ¿DÓNDE ESTÁ TU VIDA REALMENTE?</text>
      </svg>
    </div>
  );
}

function ImgOpcionesIngresos() {
  return (
    <div className={styles.postImgOpcionesIngresos}>
      <svg viewBox="0 0 200 120" width="200" height="120" fill="none" aria-hidden="true">
        <text x="100" y="14" fontSize="7" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle" letterSpacing="0.08em">COVERED CALLS — INGRESOS EXTRA</text>
        {/* Underlying price path */}
        <polyline
          points="20,90 50,75 80,70 110,55 140,45 170,40"
          stroke="var(--fv-ink-30)" strokeWidth="1.5" fill="none" strokeDasharray="4 3"
        />
        {/* Strike line */}
        <line x1="30" y1="45" x2="190" y2="45" stroke="var(--fv-ochre)" strokeWidth="1.5" strokeDasharray="6 3"/>
        <text x="185" y="40" fontSize="6" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="end">Strike</text>
        {/* Premium dot */}
        <circle cx="110" cy="55" r="5" fill="var(--fv-ochre)"/>
        <text x="110" y="58" fontSize="5" fill="var(--fv-paper)" fontFamily="system-ui" textAnchor="middle" fontWeight="bold">P</text>
        {/* Arrow showing premium received */}
        <line x1="110" y1="70" x2="110" y2="90" stroke="var(--fv-ochre)" strokeWidth="1.5" markerEnd="url(#arrowDown)"/>
        <text x="125" y="82" fontSize="6" fill="var(--fv-ochre)" fontFamily="system-ui">prima</text>
        <defs>
          <marker id="arrowDown" markerWidth="6" markerHeight="6" refX="3" refY="5" orient="auto">
            <path d="M0,0 L6,3 L0,6" fill="var(--fv-ochre)"/>
          </marker>
        </defs>
      </svg>
    </div>
  );
}

function ImgPea() {
  return (
    <div className={styles.postImgPea}>
      <svg viewBox="0 0 200 120" width="200" height="120" fill="none" aria-hidden="true">
        <text x="100" y="14" fontSize="7" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle" letterSpacing="0.08em">PEA — DIVIDENDOS AL 0% IRPF</text>
        {([18, 38, 58, 78, 98]).map((x, i) => {
          const heights = [22, 34, 46, 58, 70];
          return (
            <rect key={x} x={x} y={100 - heights[i]} width="14" height={heights[i]}
              fill={i === 4 ? 'var(--fv-ochre)' : 'rgba(154,107,31,0.25)'} rx="2"/>
          );
        })}
        <circle cx="160" cy="52" r="26" fill="var(--fv-ochre-ghost)" stroke="var(--fv-ochre)" strokeWidth="1.5"/>
        <text x="160" y="50" fontSize="13" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle" fontWeight="bold">0%</text>
        <text x="160" y="64" fontSize="6" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">IRPF</text>
        <text x="100" y="113" fontSize="6" fill="var(--fv-ink-30)" fontFamily="system-ui" textAnchor="middle">5 años de permanencia = exención</text>
      </svg>
    </div>
  );
}

function ImgPlanesPensiones() {
  return (
    <div className={styles.postImgPlanesPensiones}>
      <svg viewBox="0 0 200 120" width="200" height="120" fill="none" aria-hidden="true">
        <text x="100" y="12" fontSize="7" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle" letterSpacing="0.08em">PLAN DE PENSIONES — FLUJO FISCAL</text>
        {/* Contribution box */}
        <rect x="10" y="30" width="50" height="60" rx="6" stroke="var(--fv-ochre)" strokeWidth="1.5" fill="var(--fv-ochre-ghost)"/>
        <text x="35" y="48" fontSize="7" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">Aportas</text>
        <text x="35" y="62" fontSize="9" fill="var(--fv-ink)" fontFamily="system-ui" textAnchor="middle">1.500€</text>
        <text x="35" y="76" fontSize="6" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">reducción</text>
        {/* Arrow */}
        <line x1="60" y1="60" x2="80" y2="60" stroke="var(--fv-ochre)" strokeWidth="1.5" markerEnd="url(#ppArrow)"/>
        {/* Growth box */}
        <rect x="80" y="30" width="50" height="60" rx="6" stroke="var(--fv-ink-20)" strokeWidth="1" fill="none"/>
        <text x="105" y="48" fontSize="7" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">Crece</text>
        <text x="105" y="62" fontSize="9" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">25 años</text>
        <text x="105" y="76" fontSize="6" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">diferido</text>
        {/* Arrow to rescue */}
        <line x1="130" y1="60" x2="150" y2="60" stroke="var(--fv-ink-30)" strokeWidth="1" strokeDasharray="3 2"/>
        {/* Rescue box */}
        <rect x="150" y="30" width="40" height="60" rx="6" stroke="var(--fv-ochre)" strokeWidth="1.5" fill="var(--fv-ochre-ghost)"/>
        <text x="170" y="48" fontSize="7" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">Rescate</text>
        <text x="170" y="62" fontSize="9" fill="var(--fv-ink)" fontFamily="system-ui" textAnchor="middle">70K€</text>
        <text x="170" y="76" fontSize="6" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">trabajo</text>
        <defs>
          <marker id="ppArrow" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
            <path d="M0,0 L6,3 L0,6" fill="var(--fv-ochre)"/>
          </marker>
        </defs>
      </svg>
    </div>
  );
}

function ImgPlanificacionFiscalFinAno() {
  return (
    <div className={styles.postImgPlanificacionFiscalFinAno}>
      <svg viewBox="0 0 200 120" width="200" height="120" fill="none" aria-hidden="true">
        <text x="100" y="12" fontSize="7" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle" letterSpacing="0.08em">PLANIFICACIÓN FISCAL — CIERRE ANUAL</text>
        {/* December box */}
        <rect x="10" y="28" width="55" height="65" rx="6" stroke="var(--fv-ochre)" strokeWidth="1.5" fill="var(--fv-ochre-ghost)"/>
        <text x="37" y="44" fontSize="7" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">Dic</text>
        <text x="37" y="58" fontSize="6" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">Vender</text>
        <text x="37" y="72" fontSize="6" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">pérdidas</text>
        <text x="37" y="84" fontSize="8" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">−1.200€</text>
        {/* Arrow */}
        <line x1="65" y1="60" x2="85" y2="60" stroke="var(--fv-ochre)" strokeWidth="1.5"/>
        <polygon points="83,56 89,60 83,64" fill="var(--fv-ochre)"/>
        {/* Tax saving box */}
        <rect x="88" y="38" width="55" height="50" rx="6" stroke="var(--fv-ink-20)" strokeWidth="1" fill="none"/>
        <text x="115" y="54" fontSize="7" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">Ahorro</text>
        <text x="115" y="68" fontSize="8" fill="var(--fv-ink)" fontFamily="system-ui" textAnchor="middle">252€</text>
        <text x="115" y="80" fontSize="5" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">19% s/1.200€</text>
        {/* January box */}
        <rect x="148" y="28" width="42" height="65" rx="6" stroke="var(--fv-ink-20)" strokeWidth="1" fill="none"/>
        <text x="169" y="44" fontSize="7" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">Ene</text>
        <text x="169" y="58" fontSize="6" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">+12m</text>
        <text x="169" y="72" fontSize="6" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">dinero</text>
        <text x="169" y="84" fontSize="5" fill="var(--fv-ink-30)" fontFamily="system-ui" textAnchor="middle">trabajando</text>
        {/* Bottom annotation */}
        <text x="100" y="108" fontSize="5.5" fill="var(--fv-ink-30)" fontFamily="system-ui" textAnchor="middle">Vender en dic → pagar en jun 2027 · Vender en ene → pagar en jun 2028</text>
      </svg>
    </div>
  );
}

function ImgPlusvalias() {
  return (
    <div className={styles.postImgPlusvalias}>
      <svg viewBox="0 0 200 120" width="200" height="120" fill="none" aria-hidden="true">
        <rect x="20" y="80" width="22" height="25" rx="2" fill="rgba(154,107,31,0.25)"/>
        <rect x="50" y="60" width="22" height="45" rx="2" fill="rgba(154,107,31,0.35)"/>
        <rect x="80" y="70" width="22" height="35" rx="2" fill="rgba(154,107,31,0.2)"/>
        <rect x="110" y="35" width="22" height="70" rx="2" fill="var(--fv-ochre)"/>
        <rect x="140" y="50" width="22" height="55" rx="2" fill="rgba(154,107,31,0.3)"/>
        <line x1="10" y1="108" x2="175" y2="108" stroke="var(--fv-ink-30)" strokeWidth="1.5" strokeDasharray="4 3"/>
        <polyline
          points="30,85 60,55 90,65 120,30 150,45"
          stroke="var(--fv-ochre)" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round"
        />
        <circle cx="120" cy="30" r="3" fill="var(--fv-ochre)"/>
      </svg>
    </div>
  );
}

function ImgPrimaEmision() {
  return (
    <div className={styles.postImgPrimaEmision}>
      <svg viewBox="0 0 200 120" width="200" height="120" fill="none" aria-hidden="true">
        <text x="100" y="14" fontSize="7" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle" letterSpacing="0.08em">PRIMA DE EMISIÓN — FLUJO FISCAL</text>
        {/* Company box */}
        <rect x="10" y="30" width="55" height="60" rx="6" stroke="var(--fv-ochre)" strokeWidth="1.5" fill="var(--fv-ochre-ghost)"/>
        <text x="37" y="48" fontSize="7" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">Empresa</text>
        <text x="37" y="62" fontSize="6" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">Ampliación</text>
        <text x="37" y="76" fontSize="8" fill="var(--fv-ink)" fontFamily="system-ui" textAnchor="middle">+100€</text>
        {/* Arrow */}
        <line x1="65" y1="60" x2="85" y2="60" stroke="var(--fv-ochre)" strokeWidth="1.5"/>
        {/* Investor box */}
        <rect x="85" y="30" width="55" height="60" rx="6" stroke="var(--fv-ink-20)" strokeWidth="1" fill="none"/>
        <text x="112" y="48" fontSize="7" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">Inversor</text>
        <text x="112" y="62" fontSize="6" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">recibe</text>
        <text x="112" y="76" fontSize="8" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">100€</text>
        {/* Arrow to result */}
        <line x1="140" y1="60" x2="155" y2="60" stroke="var(--fv-ink-30)" strokeWidth="1" strokeDasharray="3 2"/>
        {/* Result box */}
        <rect x="155" y="35" width="40" height="50" rx="4" stroke="var(--fv-ochre)" strokeWidth="1.5" fill="var(--fv-ochre-ghost)"/>
        <text x="175" y="52" fontSize="6" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">Base</text>
        <text x="175" y="64" fontSize="6" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">coste</text>
        <text x="175" y="78" fontSize="5" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">−100€</text>
        {/* Bottom annotation */}
        <text x="100" y="105" fontSize="5.5" fill="var(--fv-ink-30)" fontFamily="system-ui" textAnchor="middle">No tributa → reduce valor de adquisición</text>
        <text x="100" y="114" fontSize="5" fill="var(--fv-ink-20)" fontFamily="system-ui" textAnchor="middle">Exceso sobre coste → tributa como RCM</text>
      </svg>
    </div>
  );
}

function ImgPromediarBaja() {
  return (
    <div className={styles.postImgPromediarBaja}>
      <svg viewBox="0 0 200 120" width="200" height="120" fill="none" aria-hidden="true">
        <text x="100" y="13" fontSize="7" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle" letterSpacing="0.08em">PROMEDIAR A LA BAJA · GESTIONAR LA CAÍDA</text>
        {/* Cost average dashed baseline */}
        <line x1="16" y1="26" x2="184" y2="26" stroke="var(--fv-ink-30)" strokeWidth="1" strokeDasharray="3 3"/>
        <text x="16" y="33" fontSize="6" fill="var(--fv-ink-40)" fontFamily="system-ui">COSTE MEDIO</text>
        {/* Falling price staircase */}
        <path d="M16 30 L30 30 L30 52 L44 52 L44 68 L60 68" stroke="var(--fv-ochre)" strokeWidth="1.8" fill="none" strokeLinejoin="round"/>
        <path d="M60 68 L60 82 L80 82 L80 96 L98 96" stroke="var(--fv-ochre)" strokeWidth="1.8" fill="none" strokeLinejoin="round"/>
        {/* Extra buys marked */}
        <circle cx="44" cy="60" r="5" fill="var(--fv-paper,#fff8ec)" stroke="var(--fv-ochre)" strokeWidth="1.4"/>
        <text x="44" y="63" fontSize="7" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">+</text>
        <circle cx="80" cy="89" r="5" fill="var(--fv-paper,#fff8ec)" stroke="var(--fv-ochre)" strokeWidth="1.4"/>
        <text x="80" y="92" fontSize="7" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">+</text>
        {/* Decision point */}
        <text x="112" y="97" fontSize="20" fontWeight="bold" fill="var(--fv-ink)" fontFamily="system-ui" textAnchor="middle">?</text>
        {/* Split: buy more or stop */}
        <path d="M120 82 C136 60, 150 54, 162 52" stroke="var(--fv-ink-30)" strokeWidth="1.3" fill="none" strokeDasharray="2 2"/>
        <path d="M120 110 C136 114, 150 114, 162 114" stroke="var(--fv-ink-30)" strokeWidth="1.3" fill="none" strokeDasharray="2 2"/>
        <rect x="148" y="40" width="40" height="15" rx="7.5" fill="var(--fv-ochre-ghost)" stroke="var(--fv-ochre)" strokeWidth="1.4"/>
        <text x="168" y="50" fontSize="6" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">COMPRAR +</text>
        <rect x="148" y="106" width="40" height="15" rx="7.5" stroke="var(--fv-ink-40)" strokeWidth="1.3" fill="none"/>
        <text x="168" y="116" fontSize="6" fill="var(--fv-ink)" fontFamily="system-ui" textAnchor="middle">PARAR</text>
      </svg>
    </div>
  );
}

function ImgQuiebraBroker() {
  return (
    <div className={styles.postImgQuiebraBroker}>
      <svg viewBox="0 0 200 120" width="200" height="120" fill="none" aria-hidden="true">
        <text x="100" y="14" fontSize="7" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle" letterSpacing="0.08em">SEGREGACIÓN DE ACTIVOS</text>
        {/* Broker box (cracked / failing) */}
        <rect x="18" y="46" width="46" height="46" rx="4" stroke="var(--fv-ink-30)" strokeWidth="1.2" strokeDasharray="4 3" fill="none"/>
        <text x="41" y="42" fontSize="6" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">Broker</text>
        <text x="41" y="72" fontSize="10" fill="var(--fv-ink-30)" fontFamily="system-ui" textAnchor="middle">✕</text>
        {/* Shield protecting assets */}
        <path d="M100 44 L118 51 L118 72 Q118 86 100 94 Q82 86 82 72 L82 51 Z" stroke="var(--fv-ochre)" strokeWidth="2" fill="var(--fv-ochre-ghost)"/>
        <text x="100" y="70" fontSize="9" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">€</text>
        {/* Arrow: assets transferred out to new custody */}
        <line x1="64" y1="69" x2="80" y2="69" stroke="var(--fv-ink-30)" strokeWidth="1.2"/>
        <path d="M78 66 L82 69 L78 72 Z" fill="var(--fv-ink-30)"/>
        {/* New custody box */}
        <rect x="140" y="52" width="42" height="34" rx="4" stroke="var(--fv-ochre)" strokeWidth="1.5" fill="none"/>
        <text x="161" y="48" fontSize="6" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">Custodia</text>
        <text x="161" y="73" fontSize="8" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">✓</text>
        <line x1="120" y1="69" x2="138" y2="69" stroke="var(--fv-ink-30)" strokeWidth="1.2"/>
        <path d="M136 66 L140 69 L136 72 Z" fill="var(--fv-ink-30)"/>
        <line x1="24" y1="104" x2="180" y2="104" stroke="var(--fv-ink-20)" strokeWidth="0.8" strokeDasharray="3 2"/>
        <text x="100" y="115" fontSize="5.5" fill="var(--fv-ink-30)" fontFamily="system-ui" textAnchor="middle">FOGAIN: hasta 100.000 € por titular</text>
      </svg>
    </div>
  );
}

function ImgRebalanceo() {
  return (
    <div className={styles.postImgRebalanceo}>
      <svg viewBox="0 0 200 120" width="200" height="120" fill="none" aria-hidden="true">
        <text x="100" y="14" fontSize="7" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle" letterSpacing="0.08em">DERIVA DE CARTERA — REBALANCEO</text>
        {/* Left pan - overweight */}
        <rect x="7" y="32" width="55" height="55" rx="6" stroke="var(--fv-ochre)" strokeWidth="1.5" fill="var(--fv-ochre-ghost)"/>
        <text x="34" y="50" fontSize="7" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">Peso</text>
        <text x="34" y="64" fontSize="10" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">14%</text>
        <text x="34" y="76" fontSize="5" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">objetivo 5%</text>
        {/* Beam */}
        <line x1="40" y1="87" x2="155" y2="56" stroke="var(--fv-ink-30)" strokeWidth="2" strokeLinecap="round"/>
        {/* Fulcrum */}
        <polygon points="97,88 103,88 100,52" fill="var(--fv-ink-20)"/>
        {/* Right pan - underweight */}
        <rect x="145" y="22" width="48" height="34" rx="6" stroke="var(--fv-ink-20)" strokeWidth="1" fill="none"/>
        <text x="169" y="36" fontSize="7" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">Peso</text>
        <text x="169" y="48" fontSize="9" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">2%</text>
        {/* Arrow down to overweight */}
        <text x="34" y="102" fontSize="5.5" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">sobreponderado</text>
        {/* Arrow right side */}
        <text x="169" y="68" fontSize="5.5" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">infra-ponderado</text>
      </svg>
    </div>
  );
}

function ImgRecomprasVsDividendos() {
  return (
    <div className={styles.postImgRecomprasVsDividendos}>
      <svg viewBox="0 0 200 120" width="200" height="120" fill="none" aria-hidden="true">
        <text x="100" y="13" fontSize="7" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle" letterSpacing="0.08em">ACCIONES EN CIRCULACIÓN</text>
        {/* Shrinking pie: shares outstanding reduced by buybacks */}
        <circle cx="52" cy="66" r="30" fill="none" stroke="var(--fv-ink-30)" strokeWidth="1.5"/>
        <path d="M52 36 A30 30 0 0 1 82 66 L52 66 Z" fill="var(--fv-ochre-ghost)" stroke="var(--fv-ochre)" strokeWidth="1.5"/>
        <text x="66" y="56" fontSize="6" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">−25%</text>
        <text x="52" y="106" fontSize="6" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">recompradas</text>
        {/* Arrow to bigger slice per shareholder */}
        <path d="M92 66 L114 66" stroke="var(--fv-ochre)" strokeWidth="1.5" strokeDasharray="3 2"/>
        <path d="M110 62 L116 66 L110 70" fill="none" stroke="var(--fv-ochre)" strokeWidth="1.5"/>
        {/* Coins column: dividend vs buyback split */}
        <rect x="122" y="30" width="66" height="32" rx="5" stroke="var(--fv-ink-20)" strokeWidth="1" fill="none"/>
        <circle cx="134" cy="46" r="6" fill="var(--fv-ochre-ghost)" stroke="var(--fv-ochre)" strokeWidth="1"/>
        <text x="160" y="43" fontSize="6" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">Dividendo</text>
        <text x="160" y="53" fontSize="5.5" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">tributa al cobro</text>
        <rect x="122" y="68" width="66" height="32" rx="5" stroke="var(--fv-ochre)" strokeWidth="1.5" fill="var(--fv-ochre-ghost)"/>
        <polygon points="128,92 140,74 134,92" fill="var(--fv-ochre)"/>
        <text x="160" y="81" fontSize="6" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">Recompra</text>
        <text x="160" y="91" fontSize="5.5" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">difiere el IRPF</text>
        <text x="100" y="116" fontSize="5.5" fill="var(--fv-ink-30)" fontFamily="system-ui" textAnchor="middle">Shareholder yield = dividendo + recompra neta</text>
      </svg>
    </div>
  );
}

function ImgReglaChowder() {
  return (
    <div className={styles.postImgReglaChowder}>
      <svg viewBox="0 0 200 120" width="200" height="120" fill="none" aria-hidden="true">
        <text x="100" y="14" fontSize="7" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle" letterSpacing="0.08em">NÚMERO DE CHOWDER</text>
        {/* Yield block */}
        <rect x="24" y="60" width="34" height="30" rx="4" stroke="var(--fv-ochre)" strokeWidth="1.5" fill="var(--fv-ochre-ghost)"/>
        <text x="41" y="56" fontSize="6" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">Yield</text>
        <text x="41" y="79" fontSize="8" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">2,8%</text>
        {/* Plus */}
        <text x="70" y="79" fontSize="12" fill="var(--fv-ink-30)" fontFamily="system-ui" textAnchor="middle">+</text>
        {/* Growth block */}
        <rect x="82" y="60" width="34" height="30" rx="4" stroke="var(--fv-ink-30)" strokeWidth="1.2" fill="none"/>
        <text x="99" y="56" fontSize="6" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">Crec. 5a</text>
        <text x="99" y="79" fontSize="8" fill="var(--fv-ink)" fontFamily="system-ui" textAnchor="middle">8%</text>
        {/* Equals */}
        <text x="128" y="79" fontSize="12" fill="var(--fv-ink-30)" fontFamily="system-ui" textAnchor="middle">=</text>
        {/* Result block */}
        <rect x="140" y="52" width="40" height="38" rx="4" stroke="var(--fv-ochre)" strokeWidth="2" fill="var(--fv-ochre-ghost)"/>
        <text x="160" y="48" fontSize="6" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">Chowder</text>
        <text x="160" y="78" fontSize="12" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">10,8</text>
        {/* Threshold line */}
        <line x1="24" y1="102" x2="180" y2="102" stroke="var(--fv-ink-20)" strokeWidth="0.8" strokeDasharray="3 2"/>
        <text x="100" y="114" fontSize="5.5" fill="var(--fv-ink-30)" fontFamily="system-ui" textAnchor="middle">Corte: 12 general · 8 para utilities</text>
      </svg>
    </div>
  );
}

function ImgReinvertirDividendos() {
  return (
    <div className={styles.postImgReinvertirDividendos}>
      <svg viewBox="0 0 200 120" width="200" height="120" fill="none" aria-hidden="true">
        <text x="100" y="14" fontSize="7" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle" letterSpacing="0.08em">REINVERTIR vs COBRAR</text>
        {/* Money in */}
        <rect x="10" y="30" width="50" height="60" rx="6" stroke="var(--fv-ochre)" strokeWidth="1.5" fill="var(--fv-ochre-ghost)"/>
        <text x="35" y="48" fontSize="7" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">Cobrar</text>
        <text x="35" y="62" fontSize="8" fill="var(--fv-ink)" fontFamily="system-ui" textAnchor="middle">2.000€</text>
        <text x="35" y="76" fontSize="6" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">−19% IRPF</text>
        <text x="35" y="86" fontSize="8" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">1.620€</text>
        {/* Arrow */}
        <line x1="60" y1="60" x2="80" y2="60" stroke="var(--fv-ink-30)" strokeWidth="1" strokeDasharray="3 2"/>
        {/* Reinvest box */}
        <rect x="80" y="30" width="50" height="60" rx="6" stroke="var(--fv-ink-20)" strokeWidth="1" fill="none"/>
        <text x="105" y="48" fontSize="7" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">Fondo</text>
        <text x="105" y="62" fontSize="8" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">2.000€</text>
        <text x="105" y="76" fontSize="6" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">acumulación</text>
        <text x="105" y="86" fontSize="8" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">diferido</text>
        {/* Result */}
        <rect x="140" y="30" width="50" height="60" rx="6" stroke="var(--fv-ochre)" strokeWidth="1.5" fill="var(--fv-ochre-ghost)"/>
        <text x="165" y="48" fontSize="7" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">20 años</text>
        <text x="165" y="62" fontSize="10" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">+38%</text>
        <text x="165" y="76" fontSize="6" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">vs cobrar</text>
        <text x="165" y="86" fontSize="5" fill="var(--fv-ink-30)" fontFamily="system-ui" textAnchor="middle">diferimiento</text>
      </svg>
    </div>
  );
}

function ImgReitsExtranjeros() {
  return (
    <div className={styles.postImgReitsExtranjeros}>
      <svg viewBox="0 0 200 120" width="200" height="120" fill="none" aria-hidden="true">
        <text x="100" y="12" fontSize="7" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle" letterSpacing="0.08em">REITs EXTRANJEROS — FISCALIDAD IRPF</text>
        {/* US REIT */}
        <rect x="15" y="30" width="45" height="60" rx="6" stroke="var(--fv-ochre)" strokeWidth="1.5" fill="var(--fv-ochre-ghost)"/>
        <text x="37" y="48" fontSize="7" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">EE.UU.</text>
        <text x="37" y="62" fontSize="6" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">Realty</text>
        <text x="37" y="74" fontSize="6" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">Income</text>
        <text x="37" y="84" fontSize="5" fill="var(--fv-ink-30)" fontFamily="system-ui" textAnchor="middle">15% ret.</text>
        {/* Germany REIT */}
        <rect x="75" y="30" width="45" height="60" rx="6" stroke="var(--fv-ink-20)" strokeWidth="1" fill="none"/>
        <text x="97" y="48" fontSize="7" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">DE</text>
        <text x="97" y="62" fontSize="6" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">Vonovia</text>
        <text x="97" y="74" fontSize="6" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">26,375%</text>
        <text x="97" y="84" fontSize="5" fill="var(--fv-ink-30)" fontFamily="system-ui" textAnchor="middle">15% CDI</text>
        {/* UK REIT */}
        <rect x="135" y="30" width="45" height="60" rx="6" stroke="var(--fv-ochre)" strokeWidth="1.5" fill="var(--fv-ochre-ghost)"/>
        <text x="157" y="48" fontSize="7" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">UK</text>
        <text x="157" y="62" fontSize="6" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">Segro</text>
        <text x="157" y="74" fontSize="6" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">0% ret.</text>
        <text x="157" y="84" fontSize="5" fill="var(--fv-ink-30)" fontFamily="system-ui" textAnchor="middle">mejor fiscal</text>
        {/* Arrows */}
        <line x1="60" y1="60" x2="75" y2="60" stroke="var(--fv-ink-30)" strokeWidth="1" strokeDasharray="3 2"/>
        <line x1="120" y1="60" x2="135" y2="60" stroke="var(--fv-ink-30)" strokeWidth="1" strokeDasharray="3 2"/>
      </svg>
    </div>
  );
}

function ImgRetencion19() {
  return (
    <div className={styles.postImgRetencion19}>
      <svg viewBox="0 0 200 120" width="200" height="120" fill="none" aria-hidden="true">
        <text x="100" y="12" fontSize="7" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle" letterSpacing="0.08em">RETENCIÓN vs TRIBUACIÓN REAL</text>
        {/* 19% bar */}
        <rect x="20" y="30" width="60" height="14" rx="3" fill="var(--fv-ochre-ghost)" stroke="var(--fv-ochre)" strokeWidth="1"/>
        <text x="50" y="40" fontSize="7" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">19% retención</text>
        {/* 28% bar */}
        <rect x="20" y="52" width="60" height="14" rx="3" fill="var(--fv-ink-10)" stroke="var(--fv-ink-20)" strokeWidth="1"/>
        <text x="50" y="62" fontSize="7" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">28% real max.</text>
        {/* Arrow */}
        <line x1="85" y1="48" x2="110" y2="48" stroke="var(--fv-ochre)" strokeWidth="1.5" strokeDasharray="3 2"/>
        <polygon points="108,44 114,48 108,52" fill="var(--fv-ochre)"/>
        {/* Difference */}
        <rect x="115" y="36" width="65" height="24" rx="5" fill="var(--fv-ochre-ghost)" stroke="var(--fv-ochre)" strokeWidth="1.5"/>
        <text x="147" y="47" fontSize="6" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">Diferencia:</text>
        <text x="147" y="57" fontSize="8" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle" fontWeight="600">hasta +9 pts</text>
        {/* Bottom scale */}
        <rect x="20" y="82" width="160" height="6" rx="3" fill="var(--fv-ink-10)"/>
        <rect x="20" y="82" width="24" height="6" rx="3" fill="var(--fv-ochre)"/>
        <rect x="44" y="82" width="36" height="6" fill="var(--fv-ochre)" opacity="0.7"/>
        <rect x="80" y="82" width="48" height="6" fill="var(--fv-ochre)" opacity="0.4"/>
        <rect x="128" y="82" width="52" height="6" fill="var(--fv-ochre)" opacity="0.2"/>
        <text x="100" y="100" fontSize="5" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">19%        21%        23%        28%</text>
        <text x="100" y="112" fontSize="5" fill="var(--fv-ink-30)" fontFamily="system-ui" textAnchor="middle">Base del ahorro →</text>
      </svg>
    </div>
  );
}

function ImgReyesDelDividendo() {
  return (
    <div className={styles.postImgReyesDelDividendo}>
      <svg viewBox="0 0 200 120" width="200" height="120" fill="none" aria-hidden="true">
        <text x="100" y="14" fontSize="7" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle" letterSpacing="0.08em">50 AÑOS · MISMO SENTIDO</text>
        {/* Up arrow = rising dividend */}
        <polyline points="20,100 50,82 80,66 110,50 140,34 170,20" stroke="var(--fv-ochre)" strokeWidth="2.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
        {/* Year ticks */}
        <text x="22" y="112" fontSize="6" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">1975</text>
        <text x="168" y="32" fontSize="6" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">2026</text>
        {/* Crown */}
        <path d="M84,8 L92,20 L100,8 L108,20 L116,8 L116,16 L84,16 Z" fill="var(--fv-ochre)" stroke="var(--fv-ink-30)" strokeWidth="0.5" />
        <text x="100" y="40" fontSize="6" fill="var(--fv-ink-30)" fontFamily="system-ui" textAnchor="middle">racha nunca rota</text>
      </svg>
    </div>
  );
}

function ImgRiesgoDivisa() {
  return (
    <div className={styles.postImgRiesgoDivisa}>
      <svg viewBox="0 0 200 120" width="200" height="120" fill="none" aria-hidden="true">
        <text x="100" y="14" fontSize="8" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle" letterSpacing="0.08em">EUR / USD</text>
        {/* Euro circle */}
        <circle cx="46" cy="62" r="26" stroke="var(--fv-ink-30)" strokeWidth="1.5" fill="none"/>
        <text x="46" y="70" fontSize="24" fill="var(--fv-ink)" fontFamily="system-ui" textAnchor="middle">€</text>
        {/* Dollar circle */}
        <circle cx="154" cy="62" r="26" stroke="var(--fv-ochre)" strokeWidth="1.5" fill="var(--fv-ochre-ghost)"/>
        <text x="154" y="70" fontSize="24" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">$</text>
        {/* Wavy exchange line between them */}
        <path d="M76,54 q12,-10 24,0 t24,0" stroke="var(--fv-ochre)" strokeWidth="2" fill="none" strokeLinecap="round" markerEnd="url(#divArrowR)"/>
        <path d="M124,72 q-12,10 -24,0 t-24,0" stroke="var(--fv-ink-40)" strokeWidth="2" fill="none" strokeLinecap="round" markerEnd="url(#divArrowL)"/>
        {/* Dividend coins falling into euro */}
        <circle cx="40" cy="102" r="4" fill="var(--fv-ochre)"/>
        <circle cx="52" cy="102" r="4" fill="rgba(154,107,31,0.35)"/>
        <text x="100" y="106" fontSize="7" fill="var(--fv-ink-30)" fontFamily="system-ui" textAnchor="middle">tu dividendo, al cambio del día</text>
        <defs>
          <marker id="divArrowR" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
            <path d="M0,0 L6,3 L0,6" fill="var(--fv-ochre)"/>
          </marker>
          <marker id="divArrowL" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
            <path d="M0,0 L6,3 L0,6" fill="var(--fv-ink-40)"/>
          </marker>
        </defs>
      </svg>
    </div>
  );
}

function ImgScripDividend() {
  return (
    <div className={styles.postImgScripDividend}>
      <svg viewBox="0 0 200 120" width="200" height="120" fill="none" aria-hidden="true">
        <text x="100" y="14" fontSize="7" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle" letterSpacing="0.08em">SCRIP DIVIDEND — 3 OPCIONES</text>
        {/* Option A: acciones */}
        <rect x="12" y="28" width="50" height="72" rx="6" stroke="var(--fv-ochre)" strokeWidth="1.5" fill="var(--fv-ochre-ghost)"/>
        <text x="37" y="44" fontSize="7" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">A</text>
        <text x="37" y="56" fontSize="6" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">Acciones</text>
        <text x="37" y="70" fontSize="6" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">nuevas</text>
        <text x="37" y="84" fontSize="5" fill="var(--fv-ink-30)" fontFamily="system-ui" textAnchor="middle">diferido</text>
        {/* Option B: venta mercado */}
        <rect x="75" y="28" width="50" height="72" rx="6" stroke="var(--fv-ink-20)" strokeWidth="1" fill="none"/>
        <text x="100" y="44" fontSize="7" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">B</text>
        <text x="100" y="56" fontSize="6" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">Vender</text>
        <text x="100" y="70" fontSize="6" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">derechos</text>
        <text x="100" y="84" fontSize="5" fill="var(--fv-ink-30)" fontFamily="system-ui" textAnchor="middle">gan. patrim.</text>
        {/* Option C: cobro efectivo */}
        <rect x="138" y="28" width="50" height="72" rx="6" stroke="var(--fv-ink-20)" strokeWidth="1" fill="none"/>
        <text x="163" y="44" fontSize="7" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">C</text>
        <text x="163" y="56" fontSize="6" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">Efectivo</text>
        <text x="163" y="70" fontSize="6" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">dividendo</text>
        <text x="163" y="84" fontSize="5" fill="var(--fv-ink-30)" fontFamily="system-ui" textAnchor="middle">casilla 29</text>
      </svg>
    </div>
  );
}

function ImgSeguridadDividendo() {
  return (
    <div className={styles.postImgSeguridadDividendo}>
      <svg viewBox="0 0 200 120" width="200" height="120" fill="none" aria-hidden="true">
        <text x="100" y="14" fontSize="7" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle" letterSpacing="0.08em">SEGURIDAD DIVIDENDO — MÉTRICAS</text>
        {/* Payout ratio gauge */}
        <rect x="15" y="30" width="50" height="70" rx="6" stroke="var(--fv-ochre)" strokeWidth="1.5" fill="var(--fv-ochre-ghost)"/>
        <text x="40" y="48" fontSize="7" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">Payout</text>
        <text x="40" y="62" fontSize="8" fill="var(--fv-ink)" fontFamily="system-ui" textAnchor="middle">65%</text>
        <text x="40" y="76" fontSize="5" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">saludable</text>
        {/* FCF coverage */}
        <rect x="75" y="30" width="50" height="70" rx="6" stroke="var(--fv-ink-20)" strokeWidth="1" fill="none"/>
        <text x="100" y="48" fontSize="7" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">FCF</text>
        <text x="100" y="62" fontSize="8" fill="var(--fv-ink)" fontFamily="system-ui" textAnchor="middle">1,4x</text>
        <text x="100" y="76" fontSize="5" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">cobertura</text>
        {/* Debt ratio */}
        <rect x="135" y="30" width="50" height="70" rx="6" stroke="var(--fv-ink-20)" strokeWidth="1" fill="none"/>
        <text x="160" y="48" fontSize="7" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">Deuda</text>
        <text x="160" y="62" fontSize="8" fill="var(--fv-ink)" fontFamily="system-ui" textAnchor="middle">3,2x</text>
        <text x="160" y="76" fontSize="5" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">EBITDA</text>
        {/* Checkmark for safe */}
        <circle cx="100" cy="110" r="6" fill="var(--fv-ochre-ghost)" stroke="var(--fv-ochre)" strokeWidth="1.5"/>
        <polyline points="96,110 99,113 104,108" stroke="var(--fv-ochre)" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round"/>
      </svg>
    </div>
  );
}

function ImgSociedadPatrimonial() {
  return (
    <div className={styles.postImgSociedadPatrimonial}>
      <svg viewBox="0 0 200 120" width="200" height="120" fill="none" aria-hidden="true">
        <text x="100" y="14" fontSize="8" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle" letterSpacing="0.08em">S.L. · DOS PEAJES</text>
        {/* Cartera (origen) */}
        <rect x="10" y="46" width="40" height="30" rx="4" stroke="var(--fv-ink-30)" strokeWidth="1.5" fill="none"/>
        <text x="30" y="65" fontSize="7" fill="var(--fv-ink)" fontFamily="system-ui" textAnchor="middle">CARTERA</text>
        {/* Peaje 1 */}
        <path d="M50,61 L74,61" stroke="var(--fv-ochre)" strokeWidth="1.5"/>
        <polygon points="74,55 90,61 74,67" fill="var(--fv-ochre)"/>
        <text x="66" y="50" fontSize="7" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">25%</text>
        {/* Sociedad */}
        <rect x="90" y="40" width="42" height="42" rx="4" stroke="var(--fv-ochre)" strokeWidth="1.5" fill="var(--fv-ochre-ghost)"/>
        <text x="111" y="65" fontSize="9" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">S.L.</text>
        {/* Peaje 2 */}
        <path d="M132,61 L152,61" stroke="var(--fv-ink-40)" strokeWidth="1.5"/>
        <polygon points="152,55 168,61 152,67" fill="var(--fv-ink-40)"/>
        <text x="146" y="50" fontSize="7" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">21%</text>
        {/* Bolsillo */}
        <rect x="168" y="48" width="24" height="26" rx="4" stroke="var(--fv-ink-30)" strokeWidth="1.5" fill="none"/>
        <text x="180" y="65" fontSize="7" fill="var(--fv-ink)" fontFamily="system-ui" textAnchor="middle">TÚ</text>
        <text x="100" y="104" fontSize="7" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">el dividendo tributa dos veces</text>
      </svg>
    </div>
  );
}

function ImgSocimi() {
  return (
    <div className={styles.postImgSocimi}>
      <svg viewBox="0 0 200 120" width="200" height="120" fill="none" aria-hidden="true">
        <text x="100" y="14" fontSize="7" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle" letterSpacing="0.08em">SOCIMI — RÉGIMEN FISCAL</text>
        {/* Building A - SOCIMI 0% */}
        <rect x="20" y="35" width="45" height="60" rx="4" stroke="var(--fv-ochre)" strokeWidth="1.5" fill="var(--fv-ochre-ghost)"/>
        <text x="42" y="52" fontSize="6" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">SOCIMI</text>
        <text x="42" y="65" fontSize="8" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">0%</text>
        <text x="42" y="78" fontSize="5" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">Sociedades</text>
        {/* Arrow */}
        <line x1="65" y1="65" x2="80" y2="65" stroke="var(--fv-ink-30)" strokeWidth="1" strokeDasharray="3 2"/>
        {/* Investor box */}
        <rect x="80" y="45" width="50" height="50" rx="4" stroke="var(--fv-ink-20)" strokeWidth="1" fill="none"/>
        <text x="105" y="62" fontSize="6" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">Inversor</text>
        <text x="105" y="76" fontSize="8" fill="var(--fv-ink)" fontFamily="system-ui" textAnchor="middle">19-30%</text>
        <text x="105" y="88" fontSize="5" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">Base ahorro</text>
        {/* Building B - Normal 25% */}
        <rect x="140" y="35" width="45" height="60" rx="4" stroke="var(--fv-ink-20)" strokeWidth="1" fill="none"/>
        <text x="162" y="52" fontSize="6" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">Normal</text>
        <text x="162" y="65" fontSize="8" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">25%</text>
        <text x="162" y="78" fontSize="5" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">Sociedades</text>
        {/* Bottom annotation */}
        <text x="100" y="108" fontSize="5.5" fill="var(--fv-ink-30)" fontFamily="system-ui" textAnchor="middle">Más dividendo bruto → mismo IRPF que otra acción</text>
      </svg>
    </div>
  );
}

function ImgSplitsFusiones() {
  return (
    <div className={styles.postImgSplitsFusiones}>
      <svg viewBox="0 0 200 120" width="200" height="120" fill="none" aria-hidden="true">
        <text x="100" y="14" fontSize="8" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle" letterSpacing="0.08em">RATIO 4 : 1</text>
        {/* One big share block on the left */}
        <rect x="14" y="42" width="34" height="46" rx="4" stroke="var(--fv-ink-30)" strokeWidth="1.5" fill="none"/>
        <text x="31" y="69" fontSize="9" fill="var(--fv-ink)" fontFamily="system-ui" textAnchor="middle">1</text>
        {/* Splitting fan of lines */}
        <path d="M48,65 L74,44" stroke="var(--fv-ochre)" strokeWidth="1.2"/>
        <path d="M48,65 L74,58" stroke="var(--fv-ochre)" strokeWidth="1.2"/>
        <path d="M48,65 L74,72" stroke="var(--fv-ochre)" strokeWidth="1.2"/>
        <path d="M48,65 L74,86" stroke="var(--fv-ochre)" strokeWidth="1.2"/>
        {/* Four smaller blocks */}
        <rect x="76" y="38" width="16" height="14" rx="2" fill="var(--fv-ochre)"/>
        <rect x="76" y="54" width="16" height="14" rx="2" fill="rgba(154,107,31,0.55)"/>
        <rect x="76" y="70" width="16" height="14" rx="2" fill="rgba(154,107,31,0.35)"/>
        <rect x="76" y="86" width="16" height="14" rx="2" fill="rgba(154,107,31,0.2)"/>
        {/* Equals sign */}
        <path d="M102,62 L114,62 M102,70 L114,70" stroke="var(--fv-ink-40)" strokeWidth="1.5"/>
        {/* Cost box unchanged */}
        <rect x="124" y="44" width="62" height="44" rx="4" stroke="var(--fv-ochre)" strokeWidth="1.5" fill="var(--fv-ochre-ghost)"/>
        <text x="155" y="62" fontSize="7" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">COSTE TOTAL</text>
        <text x="155" y="78" fontSize="11" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">40.000 €</text>
        <text x="100" y="112" fontSize="7" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">más títulos, mismo dinero invertido</text>
      </svg>
    </div>
  );
}

function ImgTiposInteres() {
  return (
    <div className={styles.postImgTiposInteres}>
      <svg viewBox="0 0 200 120" width="200" height="120" fill="none" aria-hidden="true">
        <text x="100" y="14" fontSize="7" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle" letterSpacing="0.08em">TIPOS BCE — PRECIO DEL DINERO</text>
        {/* rate staircase rising */}
        <polyline
          points="20,95 50,95 50,80 90,80 90,62 130,62 130,44 170,44"
          stroke="var(--fv-ochre)" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round"
        />
        {([95, 80, 62, 44]).map((y, i) => (
          <circle key={y} cx={[50, 90, 130, 170][i]} cy={y} r="3" fill="var(--fv-ochre)" />
        ))}
        {/* baseline */}
        <line x1="20" y1="105" x2="180" y2="105" stroke="var(--fv-ink-15)" strokeWidth="1" strokeDasharray="4 3" />
        <text x="100" y="116" fontSize="5.5" fill="var(--fv-ink-30)" fontFamily="system-ui" textAnchor="middle">Tipos arriba · banca arriba · utilities y SOCIMIs abajo</text>
      </svg>
    </div>
  );
}

function ImgTotalReturn() {
  return (
    <div className={styles.postImgTotalReturn}>
      <svg viewBox="0 0 200 120" width="200" height="120" fill="none" aria-hidden="true">
        <text x="100" y="14" fontSize="7" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle" letterSpacing="0.08em">TOTAL RETURN = DIVIDENDO + PRECIO</text>
        {/* Dividend bar */}
        <rect x="30" y="50" width="30" height="50" rx="4" stroke="var(--fv-ochre)" strokeWidth="1.5" fill="var(--fv-ochre-ghost)"/>
        <text x="45" y="46" fontSize="6" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">Div.</text>
        <text x="45" y="98" fontSize="7" fill="var(--fv-ink)" fontFamily="system-ui" textAnchor="middle">+5%</text>
        {/* Price change bar */}
        <rect x="85" y="65" width="30" height="35" rx="4" stroke="var(--fv-ink-20)" strokeWidth="1" fill="none"/>
        <text x="100" y="61" fontSize="6" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">Precio</text>
        <text x="100" y="98" fontSize="7" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">+8%</text>
        {/* Plus sign */}
        <text x="70" y="76" fontSize="10" fill="var(--fv-ink-30)" fontFamily="system-ui" textAnchor="middle">+</text>
        {/* Total return bar */}
        <rect x="140" y="35" width="30" height="65" rx="4" stroke="var(--fv-ochre)" strokeWidth="1.5" fill="var(--fv-ochre-ghost)"/>
        <text x="155" y="31" fontSize="6" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">Total</text>
        <text x="155" y="98" fontSize="8" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">+13%</text>
        {/* Arrow from dividend to total */}
        <line x1="60" y1="75" x2="75" y2="75" stroke="var(--fv-ink-30)" strokeWidth="1" strokeDasharray="3 2"/>
        {/* Arrow from price to total */}
        <line x1="115" y1="75" x2="130" y2="75" stroke="var(--fv-ink-30)" strokeWidth="1" strokeDasharray="3 2"/>
        {/* Bottom annotation */}
        <text x="100" y="115" fontSize="5.5" fill="var(--fv-ink-30)" fontFamily="system-ui" textAnchor="middle">El yield del 5% no cuenta la subida del 8%</text>
      </svg>
    </div>
  );
}

function ImgTramo30() {
  return (
    <div className={styles.postImgTramo30}>
      <svg viewBox="0 0 200 120" width="200" height="120" fill="none" aria-hidden="true">
        <text x="100" y="14" fontSize="7" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle" letterSpacing="0.08em">BASE DEL AHORRO 2025 — NUEVO TRAMO</text>
        {/* Bar 1 */}
        <rect x="15" y="70" width="28" height="30" rx="3" fill="rgba(154,107,31,0.2)"/>
        <text x="29" y="66" fontSize="6" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">19%</text>
        <text x="29" y="88" fontSize="5" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">6K</text>
        {/* Bar 2 */}
        <rect x="48" y="55" width="28" height="45" rx="3" fill="rgba(154,107,31,0.25)"/>
        <text x="62" y="51" fontSize="6" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">21%</text>
        <text x="62" y="88" fontSize="5" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">50K</text>
        {/* Bar 3 */}
        <rect x="81" y="40" width="28" height="60" rx="3" fill="rgba(154,107,31,0.3)"/>
        <text x="95" y="36" fontSize="6" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">23%</text>
        <text x="95" y="88" fontSize="5" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">200K</text>
        {/* Bar 4 */}
        <rect x="114" y="30" width="28" height="70" rx="3" fill="rgba(154,107,31,0.35)"/>
        <text x="128" y="26" fontSize="6" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">27%</text>
        <text x="128" y="88" fontSize="5" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">300K</text>
        {/* Bar 5 - new 30% */}
        <rect x="147" y="22" width="38" height="78" rx="3" fill="var(--fv-ochre)"/>
        <text x="166" y="18" fontSize="7" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle" fontWeight="bold">30%</text>
        <text x="166" y="42" fontSize="5" fill="var(--fv-ink)" fontFamily="system-ui" textAnchor="middle">nuevo</text>
        <text x="166" y="88" fontSize="5" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">&gt;300K</text>
        {/* Arrow pointing to new bar */}
        <line x1="166" y1="100" x2="166" y2="108" stroke="var(--fv-ochre)" strokeWidth="1"/>
      </svg>
    </div>
  );
}

function ImgTrampasDividendo() {
  return (
    <div className={styles.postImgTrampasDividendo}>
      <svg viewBox="0 0 200 120" width="200" height="120" fill="none" aria-hidden="true">
        <text x="100" y="12" fontSize="7" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle" letterSpacing="0.08em">YIELD TRAP — SEÑALES DE ALERTA</text>
        {/* High yield bar with warning */}
        <rect x="15" y="25" width="35" height="70" rx="4" stroke="var(--fv-ochre)" strokeWidth="1.5" fill="var(--fv-ochre-ghost)"/>
        <text x="32" y="42" fontSize="6" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">Yield</text>
        <text x="32" y="56" fontSize="9" fill="var(--fv-ink)" fontFamily="system-ui" textAnchor="middle">12%</text>
        <text x="32" y="70" fontSize="5" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">insostenible</text>
        {/* Warning triangle */}
        <polygon points="70,95 85,60 100,95" fill="none" stroke="var(--fv-ochre)" strokeWidth="1.5"/>
        <text x="85" y="85" fontSize="10" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">!</text>
        {/* Sustainable bar */}
        <rect x="115" y="40" width="35" height="55" rx="4" stroke="var(--fv-ink-20)" strokeWidth="1" fill="none"/>
        <text x="132" y="56" fontSize="6" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">Yield</text>
        <text x="132" y="70" fontSize="9" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">5%</text>
        <text x="132" y="84" fontSize="5" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">sostenible</text>
        {/* Arrow from trap to safe */}
        <line x1="50" y1="60" x2="115" y2="60" stroke="var(--fv-ink-30)" strokeWidth="1" strokeDasharray="3 2"/>
        <text x="82" y="55" fontSize="5" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle">payout, FCF</text>
        {/* Bottom annotation */}
        <text x="100" y="112" fontSize="5.5" fill="var(--fv-ink-30)" fontFamily="system-ui" textAnchor="middle">Payout &gt; 90% + FCF no cubye = señal de peligro</text>
      </svg>
    </div>
  );
}

function ImgTraspasoBrokers() {
  return (
    <div className={styles.postImgTraspasoBrokers}>
      <svg viewBox="0 0 200 120" width="200" height="120" fill="none" aria-hidden="true">
        <text x="100" y="12" fontSize="6.5" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle" letterSpacing="0.08em">TRASPASO DE VALORES — SIN VENTA</text>
        {/* Origin broker: moving box with shares */}
        <rect x="16" y="34" width="52" height="56" rx="5" stroke="var(--fv-ink-30)" strokeWidth="1.2" fill="none"/>
        <text x="42" y="30" fontSize="6" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">Broker A</text>
        <rect x="26" y="46" width="14" height="10" rx="2" fill="var(--fv-ochre-ghost)" stroke="var(--fv-ochre)" strokeWidth="1"/>
        <rect x="44" y="46" width="14" height="10" rx="2" fill="var(--fv-ochre-ghost)" stroke="var(--fv-ochre)" strokeWidth="1"/>
        <rect x="26" y="62" width="14" height="10" rx="2" fill="var(--fv-ochre-ghost)" stroke="var(--fv-ochre)" strokeWidth="1"/>
        <rect x="44" y="62" width="14" height="10" rx="2" fill="none" stroke="var(--fv-ink-30)" strokeWidth="1" strokeDasharray="2 2"/>
        {/* Truck arrow carrying a share box */}
        <line x1="72" y1="62" x2="122" y2="62" stroke="var(--fv-ochre)" strokeWidth="2"/>
        <path d="M120 57 L128 62 L120 67 Z" fill="var(--fv-ochre)"/>
        <rect x="88" y="50" width="16" height="11" rx="2" fill="var(--fv-ochre-ghost)" stroke="var(--fv-ochre)" strokeWidth="1.2"/>
        {/* Destination broker */}
        <rect x="132" y="34" width="52" height="56" rx="5" stroke="var(--fv-ochre)" strokeWidth="1.5" fill="none"/>
        <text x="158" y="30" fontSize="6" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">Broker B</text>
        <rect x="142" y="46" width="14" height="10" rx="2" fill="var(--fv-ochre-ghost)" stroke="var(--fv-ochre)" strokeWidth="1"/>
        <text x="158" y="79" fontSize="8" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">✓</text>
        {/* Tax toll crossed out */}
        <line x1="20" y1="104" x2="180" y2="104" stroke="var(--fv-ink-20)" strokeWidth="0.8" strokeDasharray="3 2"/>
        <text x="100" y="115" fontSize="5.5" fill="var(--fv-ink-30)" fontFamily="system-ui" textAnchor="middle">0 € de IRPF · mismo precio de compra · FIFO intacto</text>
      </svg>
    </div>
  );
}

function ImgVivirDividendos() {
  return (
    <div className={styles.postImgVivirDividendos}>
      <svg viewBox="0 0 200 120" width="200" height="120" fill="none" aria-hidden="true">
        {/* Stacked coins / money bags abstract representation */}
        <rect x="40" y="70" width="120" height="30" rx="6" fill="var(--fv-ochre-ghost)" stroke="var(--fv-ochre)" strokeWidth="1.5"/>
        <rect x="50" y="50" width="100" height="30" rx="6" fill="rgba(154,107,31,0.15)" stroke="var(--fv-ochre)" strokeWidth="1"/>
        <rect x="60" y="30" width="80" height="30" rx="6" fill="rgba(154,107,31,0.25)" stroke="var(--fv-ochre)" strokeWidth="1"/>
        <text x="100" y="115" fontSize="7" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle" letterSpacing="0.08em">VIVIR DE DIVIDENDOS</text>
      </svg>
    </div>
  );
}

function ImgW8ben() {
  return (
    <div className={styles.postImgW8ben}>
      <svg viewBox="0 0 200 120" width="200" height="120" fill="none" aria-hidden="true">
        <text x="100" y="12" fontSize="6.5" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle" letterSpacing="0.08em">FORM W-8BEN — RESIDENTE NO USA</text>
        {/* Document outline */}
        <rect x="38" y="20" width="124" height="86" rx="6" stroke="var(--fv-ochre)" strokeWidth="1.5" fill="var(--fv-ochre-ghost)"/>
        <line x1="52" y1="34" x2="148" y2="34" stroke="var(--fv-ink-30)" strokeWidth="1"/>
        <line x1="52" y1="46" x2="132" y2="46" stroke="var(--fv-ink-20)" strokeWidth="1"/>
        <line x1="52" y1="58" x2="120" y2="58" stroke="var(--fv-ink-20)" strokeWidth="1"/>
        <text x="52" y="74" fontSize="7" fill="var(--fv-ink-60)" fontFamily="system-ui">España · tratado 15%</text>
        {/* The two withholding figures: 30% struck, 15% kept */}
        <text x="56" y="92" fontSize="10" fill="var(--fv-ink-30)" fontFamily="system-ui" textDecoration="line-through">30%</text>
        <text x="110" y="92" fontSize="13" fill="var(--fv-ochre)" fontFamily="system-ui" fontWeight="700">15%</text>
        <text x="150" y="92" fontSize="7" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="end">origen</text>
      </svg>
    </div>
  );
}

function ImgYoc() {
  return (
    <div className={styles.postImgYoc}>
      <div className={styles.yocBars}>
        {YOC_BARS.map(({ label, value, faded, hClass }) => {
          const barCls = [styles.yocBarBlock, styles[hClass], faded ? styles.yocBarBlockFaded : ''].filter(Boolean).join(' ');
          return (
            <div key={label} className={styles.yocBar}>
              <span className={styles.yocBarValue}>{value}</span>
              <div className={barCls} />
              <span className={styles.yocBarLabel}>{label}</span>
            </div>
          );
        })}
      </div>
      <span className={styles.yocCaption}>Compra: 2018 · Hoy: 2025</span>
    </div>
  );
}

function ImgPrimaAsistenciaJunta() {
  return (
    <div className={styles.postImgPrimaAsistenciaJunta}>
      <svg viewBox="0 0 200 120" width="200" height="120" fill="none" aria-hidden="true">
        <text x="100" y="13" fontSize="6.5" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle" letterSpacing="0.08em">JUNTA · VOTO · PRIMA</text>
        <rect x="18" y="30" width="62" height="57" rx="6" stroke="var(--fv-ink-30)" strokeWidth="1.5" fill="none"/>
        <path d="M30 44h38M30 55h28M30 66h20" stroke="var(--fv-ink-20)" strokeWidth="1.5" strokeLinecap="round"/>
        <circle cx="63" cy="73" r="10" fill="var(--fv-ochre-ghost)" stroke="var(--fv-ochre)" strokeWidth="1.5"/>
        <path d="m58 73 3 3 6-7" stroke="var(--fv-ochre)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        <path d="M82 59h25" stroke="var(--fv-ochre)" strokeWidth="1.5" strokeDasharray="3 2"/>
        <path d="m103 54 7 5-7 5" fill="var(--fv-ochre)"/>
        <circle cx="147" cy="57" r="25" fill="var(--fv-ochre-ghost)" stroke="var(--fv-ochre)" strokeWidth="1.5"/>
        <text x="147" y="63" fontSize="18" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">€</text>
        <text x="147" y="96" fontSize="7" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">prima</text>
        <text x="100" y="113" fontSize="6" fill="var(--fv-ink-30)" fontFamily="system-ui" textAnchor="middle">votas · cobras · declaras el bruto</text>
      </svg>
    </div>
  );
}

export const POST_IMAGES: Record<PostSlug, PostImage> = {
  'prima-asistencia-junta-accionistas-irpf': ImgPrimaAsistenciaJunta,
  'splits-fusiones-canje-acciones-irpf': ImgSplitsFusiones,
  'dividendos-vs-alquiler-fiscalidad': ImgDividendoVsAlquiler,
  'captura-dividendo-irpf-espana': ImgCapturaDividendo,
  'dividendo-mensual': ImgDividendoMensual,
  'reyes-del-dividendo': ImgReyesDelDividendo,
  'mudarte-al-extranjero-cartera-dividendos': ImgMudarteExtranjero,
  'promediar-a-la-baja-dividendos': ImgPromediarBaja,
  'cuando-vender-acciones-dividendos': ImgCuandoVender,
  'aportaciones-periodicas-dca-dividendos': ImgAportacionesPeriodicas,
  'amortizar-hipoteca-vs-invertir': ImgAmortizarHipotecaVsInvertir,
  'intereses-cuentas-remuneradas-depositos-irpf': ImgCuentasRemuneradas,
  'bonos-renta-fija-fiscalidad-irpf': ImgBonosRentaFija,
  'sociedad-patrimonial-dividendos-espana': ImgSociedadPatrimonial,
  'cuentas-conjuntas-titularidad-dividendos-irpf': ImgCuentasConjuntas,
  'riesgo-divisa-cartera-dividendos': ImgRiesgoDivisa,
  'recompras-acciones-vs-dividendos': ImgRecomprasVsDividendos,
  'fiscalidad-opciones-irpf-espana': ImgFiscalidadOpciones,
  'traspaso-acciones-entre-brokers': ImgTraspasoBrokers,
  'formulario-w8ben-guia-espana': ImgW8ben,
  'que-pasa-si-quiebra-tu-broker': ImgQuiebraBroker,
  'regla-chowder-seleccion-dividendos': ImgReglaChowder,
  'heredar-acciones-irpf': ImgHeredarAcciones,
  'dividendos-inflacion-poder-adquisitivo': ImgDividendosInflacion,
  'tipos-interes-cartera-dividendos': ImgTiposInteres,
  'dividend-aristocrats-europa-espana-2026': ImgAristocratsEuropa,
  'plan-ahorro-largo-plazo-pea': ImgPea,
  'rebalanceo-cartera-dividendos': ImgRebalanceo,
  'impuesto-patrimonio-inversores-espana': ImgImpuestoPatrimonio,
  'analisis-sectorial-dividendos-espana-2026': ImgAnalisisSectorial,
  'mejores-etfs-dividendos-espana-2026': ImgMejoresEtfs,
  'dividendos-hacienda-foral-navarra-euskadi': ImgDividendosHaciendaForal,
  'opciones-ingresos-extra-dividendos': ImgOpcionesIngresos,
  'vivir-de-dividendos-20250707': ImgVivirDividendos,
  'metodo-dgi-construir-cartera-dividendos-20250705': ImgMetodoDgi,
  'seguridad-dividendo-metricas': ImgSeguridadDividendo,
  'total-return-vs-dividend-yield': ImgTotalReturn,
  'broker-dividendos-espana-2025': ImgBroker,
  'trampas-dividendo-yield-insostenible': ImgTrampasDividendo,
  'planificacion-fiscal-fin-ano': ImgPlanificacionFiscalFinAno,
  'retencion-19-vs-tributacion-real-irpf': ImgRetencion19,
  'dividendos-individuales-vs-etf-acumulacion-fiscal': ImgDividendosVsEtf,
  'derechos-suscripcion-preferente-irpf': ImgDerechosSuscripcion,
  'gastos-deducibles-inversion-irpf': ImgGastosDeducibles,
  'criptomonedas-irpf-espana': ImgCriptomonedas,
  'reits-extranjeros-irpf-espana': ImgReitsExtranjeros,
  'prima-emision-reduccion-capital-irpf': ImgPrimaEmision,
  'calendario-dividendos-irpf': ImgCalendarioDividendos,
  'tramo-30-base-ahorro-irpf': ImgTramo30,
  'planes-pensiones-irpf': ImgPlanesPensiones,
  'socimi-dividendos-irpf-espana': ImgSocimi,
  'reinvertir-dividendos': ImgReinvertirDividendos,
  'dividendos-extranjeros-doble-imposicion-irpf': ImgDividendosExtranjeros,
  'fondos-vs-etf-dividendos-espana': ImgFondosVsEtf,
  'scrip-dividend-irpf-espana': ImgScripDividend,
  'modelo-720-bienes-extranjero': ImgModelo720,
  'plusvalias-espana-irpf-guia': ImgPlusvalias,
  'dgi': ImgDgi,
  'declarar-dividendos-espana-guia-completa': ImgIrpf,
  'yield-on-cost': ImgYoc,
  'compensar-perdidas-ganancias-irpf': ImgCompensarPerdidas,
};
