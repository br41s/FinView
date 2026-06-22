import { PublicNav } from '@/components/PublicNav';
import { PublicFooter } from '@/components/PublicFooter';
import styles from './blog.module.css';

// ── Post images ──────────────────────────────────────────────────────────────

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

type YocBar = { label: string; value: string; faded: boolean; hClass: 'yocBarH60' | 'yocBarH112' };
const YOC_BARS: YocBar[] = [
  { label: 'YOP', value: '3.1%', faded: true,  hClass: 'yocBarH60'  },
  { label: 'YOC', value: '8.4%', faded: false, hClass: 'yocBarH112' },
];

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

function ImgTasaTobin() {
  return (
    <div className={styles.postImgTasaTobin}>
      <svg viewBox="0 0 200 120" width="200" height="120" fill="none" aria-hidden="true">
        <text x="100" y="14" fontSize="7" fill="var(--fv-ink-40)" fontFamily="system-ui" textAnchor="middle" letterSpacing="0.08em">TASA TOBIN — 0,2% SOBRE COMPRA</text>
        {/* Purchase box */}
        <rect x="15" y="30" width="70" height="70" rx="6" stroke="var(--fv-ochre)" strokeWidth="1.5" fill="var(--fv-ochre-ghost)"/>
        <text x="50" y="48" fontSize="7" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">Compra</text>
        <text x="50" y="62" fontSize="6" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">Santander</text>
        <text x="50" y="76" fontSize="8" fill="var(--fv-ink)" fontFamily="system-ui" textAnchor="middle">50.000€</text>
        <text x="50" y="88" fontSize="5" fill="var(--fv-ink-30)" fontFamily="system-ui" textAnchor="middle">acción española</text>
        {/* Arrow with tax */}
        <line x1="85" y1="65" x2="105" y2="65" stroke="var(--fv-ochre)" strokeWidth="1.5"/>
        <text x="95" y="58" fontSize="7" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">0,2%</text>
        {/* Tax box */}
        <rect x="110" y="40" width="50" height="50" rx="4" stroke="var(--fv-ink-20)" strokeWidth="1" fill="none"/>
        <text x="135" y="58" fontSize="7" fill="var(--fv-ink-60)" fontFamily="system-ui" textAnchor="middle">Hacienda</text>
        <text x="135" y="72" fontSize="9" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">100€</text>
        <text x="135" y="82" fontSize="5" fill="var(--fv-ink-30)" fontFamily="system-ui" textAnchor="middle">por comprar</text>
        {/* Bottom annotation */}
        <text x="100" y="108" fontSize="5.5" fill="var(--fv-ink-30)" fontFamily="system-ui" textAnchor="middle">ETF exento → 0€ · Acción española grande → 100€</text>
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

// ── Data ─────────────────────────────────────────────────────────────────────

type Post = {
  slug: string;
  tag: string;
  date: string;
  readTime: string;
  title: string;
  excerpt: string;
  Image: () => React.ReactElement;
};

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

const POSTS: Post[] = [
  {
    slug: 'criptomonedas-irpf-espana',
    tag: 'Fiscal',
    date: '23 jun 2026',
    readTime: '16 min',
    title: 'Criptomonedas en el IRPF: guía completa para declarar en España 2026',
    excerpt: 'Cómo tributan las criptomonedas en el IRPF: venta, permuta, staking, modelo 721, FIFO, casillas 1800-1814, DAC8 y ejemplos con números reales.',
    Image: ImgCriptomonedas,
  },
  {
    slug: 'tramo-30-base-ahorro-irpf',
    tag: 'Fiscal',
    date: '18 jun 2026',
    readTime: '15 min',
    title: 'El nuevo tramo del 30% en la base del ahorro: cómo te afecta en la Renta 2026',
    excerpt: 'La Ley 7/2024 subió el último tramo del ahorro del 28% al 30% para rentas superiores a 300.000 €. Guía completa con ejemplos, estrategias de planificación y cómo minimizar el impacto en tu declaración.',
    Image: ImgTramo30,
  },
  {
    slug: 'tasa-tobin-espana-2026',
    tag: 'Fiscal',
    date: '18 jun 2026',
    readTime: '14 min',
    title: 'Tasa Tobin en España 2026: el impuesto del 0,2% que pagas al comprar Santander, Iberdrola o Telefónica',
    excerpt: 'Guía completa del Impuesto sobre Transacciones Financieras: lista de empresas afectadas en 2026, cuánto pagas en cada compra, qué está exento, diferencias con otros impuestos y cómo afecta a tu estrategia de dividendos.',
    Image: ImgTasaTobin,
  },
  {
    slug: 'socimis-dividendos-irpf-espana',
    tag: 'Fiscal',
    date: '17 jun 2026',
    readTime: '15 min',
    title: 'SOCIMIs en España: guía completa de fiscalidad para el inversor en dividendos',
    excerpt: 'Todo sobre las SOCIMIs: qué son, requisitos, el régimen al 0% en Sociedades, cómo tributan los dividendos en tu IRPF, las principales SOCIMIs del mercado, errores frecuentes y cómo encajan en una cartera DGI.',
    Image: ImgSocimi,
  },
  {
    slug: 'planes-pensiones-irpf',
    tag: 'Fiscal',
    date: '17 jun 2026',
    readTime: '18 min',
    title: 'Planes de pensiones en el IRPF: guía completa 2026 — límites, fiscalidad al rescate y ejemplos',
    excerpt: 'Todo sobre los planes de pensiones en el IRPF: límites de aportación (1.500 €, autónomos, planes de empleo, cónyuge), fiscalidad al rescate como rendimiento del trabajo, PPA vs plan vs fondo de inversión y errores que te cuestan dinero.',
    Image: ImgPlanesPensiones,
  },
  {
    slug: 'socimi-dividendos-irpf-espana',
    tag: 'Fiscal',
    date: '16 jun 2026',
    readTime: '15 min',
    title: 'SOCIMIs en España: guía completa de fiscalidad en el IRPF para el inversor de dividendos',
    excerpt: 'Cómo tributan los dividendos de SOCIMIs en el IRPF: retención del 19%, gravamen especial del 19% para socios relevantes, régimen al 0% en Impuesto sobre Sociedades, comparativa fiscal con acciones y errores frecuentes al declarar.',
    Image: ImgSocimi,
  },
  {
    slug: 'reinvertir-dividendos-vs-cobrar-efectivo',
    tag: 'Estrategia',
    date: '15 jun 2026',
    readTime: '14 min',
    title: 'Reinvertir dividendos o cobrarlos en efectivo: qué es fiscalmente mejor en España',
    excerpt: 'Análisis con números reales sobre si conviene reinvertir dividendos (DRIP), usar fondos de acumulación o cobrar en efectivo. Fiscalidad IRPF, interés compuesto, ejemplos con 50.000€ y cuál elegir según tu situación.',
    Image: ImgReinvertirDividendos,
  },
  {
    slug: 'dividendos-extranjeros-doble-imposicion-irpf',
    tag: 'Fiscal',
    date: '15 jun 2026',
    readTime: '16 min',
    title: 'Dividendos extranjeros en el IRPF: cómo recuperar la doble imposición',
    excerpt: 'Guía práctica para declarar dividendos de acciones extranjeras en España: casilla 0029 y 0588, formulario W-8BEN, retenciones por país, exceso reclamable y ejemplos con IBKR, DeGiro y eToro.',
    Image: ImgDividendosExtranjeros,
  },
  {
    slug: 'fondos-vs-etf-dividendos-espana',
    tag: 'Fiscal',
    date: '14 jun 2026',
    readTime: '15 min',
    title: 'Fondos de inversión vs ETFs de dividendos: la diferencia fiscal que te está costando dinero',
    excerpt: 'La diferencia fiscal entre fondos y ETFs de dividendos en España puede suponer miles de euros a lo largo de los años. Traspasos, tributación, ejemplos reales y cuál elegir según tu estrategia.',
    Image: ImgFondosVsEtf,
  },
  {
    slug: 'scrip-dividend-irpf-espana',
    tag: 'Fiscal',
    date: '13 jul 2026',
    readTime: '14 min',
    title: 'Scrip dividend en España: qué es, cómo funciona y fiscalidad en el IRPF',
    excerpt: 'Guía completa sobre el scrip dividend o dividendo flexible: las 3 opciones del accionista (acciones nuevas, vender derechos o cobro en efectivo), tratamiento fiscal distinto para cada una, ejemplos con Telefónica y Repsol, y errores que te pueden costar dinero.',
    Image: ImgScripDividend,
  },
  {
    slug: 'modelo-720-bienes-extranjero',
    tag: 'Fiscal',
    date: '7 jul 2026',
    readTime: '16 min',
    title: 'Modelo 720: guía completa para declarar bienes en el extranjero',
    excerpt: 'Todo sobre el Modelo 720: quién está obligado, los tres bloques (cuentas, valores e inmuebles), umbrales de 50.000 €, plazos, sanciones tras la sentencia del TJUE y cómo declarar tus posiciones en brokers extranjeros como IBKR, DeGiro o eToro.',
    Image: ImgModelo720,
  },
  {
    slug: 'plusvalias-espana-irpf-guia',
    tag: 'Fiscal',
    date: '18 jun 2026',
    readTime: '14 min',
    title: 'Cómo tributan las plusvalías en España: guía completa IRPF',
    excerpt: 'Guía definitiva sobre la fiscalidad de las plusvalías en España: tributación de ganancias patrimoniales por venta de acciones, compensación de pérdidas, regla de los dos meses, FIFO, plazos de arrastre y ejemplos prácticos para la Renta.',
    Image: ImgPlusvalias,
  },
  {
    slug: 'dgi',
    tag: 'Estrategia',
    date: '26 may 2026',
    readTime: '8 min',
    title: 'La estrategia DGI: cómo invertir para vivir de dividendos',
    excerpt: 'Guía definitiva para invertir en dividendos crecientes: fundamentos, selección de acciones, fiscalidad, riesgos y alternativas para alcanzar la independencia financiera.',
    Image: ImgDgi,
  },
  {
    slug: 'declarar-dividendos-espana-guia-completa',
    tag: 'Fiscal',
    date: '7 jun 2026',
    readTime: '12 min',
    title: 'Cómo declarar los dividendos en España: guía completa',
    excerpt: 'Guía definitiva para declarar dividendos en España: casillas del Modelo 100, doble imposición internacional, retenciones por país, errores frecuentes, ejemplos prácticos y todo lo que necesitas para la Renta.',
    Image: ImgIrpf,
  },
  {
    slug: 'yield-on-cost',
    tag: 'Métricas',
    date: '15 jun 2026',
    readTime: '12 min',
    title: 'Yield on cost: la métrica que los grandes inversores de dividendos miden',
    excerpt: 'Guía completa sobre el Yield on Cost (YOC): qué es, cómo se calcula, ejemplos reales con Coca-Cola, Realty Income, Apple y Johnson & Johnson, comparativa con otras métricas, errores fiscales en España y cómo usarlo para evaluar tu cartera de dividendos.',
    Image: ImgYoc,
  },
];

const SOCIAL_POSTS = [
  {
    handle: '@finviewapp',
    name: 'FinView',
    time: 'hace 2h',
    content: 'Los dividendos reinvertidos durante 20 años pueden multiplicar tu cartera por 4. No es teoría, es aritmética.\n\nFinView te muestra el progreso en tiempo real. 🌱',
    likes: 124,
    reposts: 38,
  },
  {
    handle: '@finviewapp',
    name: 'FinView',
    time: 'hace 1d',
    content: '📅 Recuerda: la campaña de la Renta 2024 termina el 30 de junio.\n\n¿Tienes tus dividendos calculados? Nosotros lo hacemos por ti.',
    likes: 87,
    reposts: 21,
  },
  {
    handle: '@finviewapp',
    name: 'FinView',
    time: 'hace 3d',
    content: 'Dato: el 80% de la rentabilidad histórica del mercado proviene de dividendos reinvertidos, no de la revalorización del precio.\n\n¿Estás aprovechando el interés compuesto? 📈',
    likes: 203,
    reposts: 67,
  },
];

// ── Icons ─────────────────────────────────────────────────────────────────────

function XIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-4.714-6.231-5.401 6.231H2.748l7.73-8.835L1.254 2.25H8.08l4.253 5.622zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>
    </svg>
  );
}

function HeartIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
      <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
    </svg>
  );
}

function RepostIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
      <polyline points="17 1 21 5 17 9"/>
      <path d="M3 11V9a4 4 0 0 1 4-4h14"/>
      <polyline points="7 23 3 19 7 15"/>
      <path d="M21 13v2a4 4 0 0 1-4 4H3"/>
    </svg>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function BlogPage() {
  return (
    <div className={styles.page}>
      <PublicNav />

      {/* ── Hero ── */}
      <section className={styles.hero}>
        <span className={styles.eyebrow}>
          <span className={styles.dot} />
          Más información
        </span>
        <h1 className={styles.h1}>
          Aprende a invertir en{' '}
          <em className={styles.em}>dividendos</em>
        </h1>
        <p className={styles.lead}>
          Estrategia, fiscalidad y métricas para el inversor de largo plazo en España.
        </p>
      </section>

      {/* ── Blog posts ── */}
      <section className={styles.postsSection}>
        <div className={styles.postsGrid}>
          {POSTS.map(({ slug, tag, date, readTime, title, excerpt, Image }) => (
            <article key={slug} className={styles.postCard}>
              <Image />
              <div className={styles.postBody}>
                <div className={styles.postMeta}>
                  <span className={styles.postTag}>{tag}</span>
                  <span className={styles.postDate}>{date} · {readTime}</span>
                </div>
                <h2 className={styles.postTitle}>{title}</h2>
                <p className={styles.postExcerpt}>{excerpt}</p>
                <a href={`/blog/${slug}`} className={styles.postLink}>Leer artículo →</a>
              </div>
            </article>
          ))}
        </div>
      </section>

      {/* ── Social feeds ── */}
      <section className={styles.socialBg}>
        <div className={styles.socialInner}>
          <div className={styles.socialHeader}>
            <div>
              <h2 className={styles.socialTitle}>En redes</h2>
              <p className={styles.socialSubtitle}>Seguimiento diario de dividendos, tips fiscales y noticias del mercado.</p>
            </div>
            <a href="https://x.com/finviewapp" target="_blank" rel="noopener noreferrer" className={styles.followBtn}>
              <XIcon /> Seguir en X
            </a>
          </div>

          <div className={styles.socialGrid}>
            {SOCIAL_POSTS.map(({ handle, name, time, content, likes, reposts }) => (
              <div key={content.slice(0, 20)} className={styles.tweet}>
                <div className={styles.tweetHeader}>
                  <div className={styles.tweetAvatar}>
                    <span className={styles.tweetAvatarLetter}>F</span>
                  </div>
                  <div className={styles.tweetInfo}>
                    <p className={styles.tweetName}>{name}</p>
                    <p className={styles.tweetHandle}>{handle}</p>
                  </div>
                  <span className={styles.tweetXIcon}><XIcon /></span>
                </div>
                <p className={styles.tweetContent}>{content}</p>
                <div className={styles.tweetFooter}>
                  <span className={styles.tweetStat}><HeartIcon /> {likes}</span>
                  <span className={styles.tweetStat}><RepostIcon /> {reposts}</span>
                  <span className={styles.tweetTime}>{time}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── CTA ── */}
      <section className={styles.ctaSection}>
        <h2 className={styles.ctaTitle}>¿Listo para ver cómo crecen tus dividendos?</h2>
        <p className={styles.ctaLead}>Importa tu cartera y ten tus métricas listas en menos de un minuto.</p>
        <div className={styles.ctaButtons}>
          <a href="/register" className={styles.ctaPrimary}>Crear cuenta gratis →</a>
          <a href="/features" className={styles.ctaSecondary}>Ver funcionalidades</a>
        </div>
      </section>

      <PublicFooter />
    </div>
  );
}
