import { PublicNav } from '@/components/PublicNav';
import { PublicFooter } from '@/components/PublicFooter';
import styles from './blog.module.css';

// ── Post images ──────────────────────────────────────────────────────────────

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

const POSTS: Post[] = [
  {
    slug: 'sociedad-patrimonial-dividendos-espana',
    tag: 'Fiscalidad',
    date: '04 ago 2026',
    readTime: '9 min',
    title: 'Sociedad patrimonial para invertir en dividendos: cuándo compensa y cuándo no',
    excerpt:
      'El 25% del Impuesto sobre Sociedades suena mejor que el IRPF hasta que sumas el segundo peaje al repartir, los costes anuales de la S.L. y descubres que la exención del 95% pide un 5% del capital que nunca vas a tener.',
    Image: ImgSociedadPatrimonial,
  },
  {
    slug: 'cuentas-conjuntas-titularidad-dividendos-irpf',
    tag: 'Fiscalidad',
    date: '02 ago 2026',
    readTime: '8 min',
    title: 'Cuentas conjuntas y titularidad: quién declara los dividendos en el IRPF',
    excerpt:
      'Tener la cuenta del broker a nombre de dos personas no es un detalle administrativo. Gananciales, presunción del 50/50, retenciones mal imputadas, cuentas de menores y usufructo: quién declara qué y con qué prueba.',
    Image: ImgCuentasConjuntas,
  },
  {
    slug: 'riesgo-divisa-cartera-dividendos',
    tag: 'Estrategia',
    date: '01 ago 2026',
    readTime: '9 min',
    title: 'Riesgo divisa en tu cartera de dividendos: por qué el euro/dólar decide parte de tu cobro',
    excerpt:
      'Si cobras dividendos de empresas USA o europeas fuera de la zona euro, el tipo de cambio mueve tu renta cada trimestre. Cuánto pesa, cómo se combina con la retención en origen y por qué cubrir la divisa casi nunca compensa en acciones.',
    Image: ImgRiesgoDivisa,
  },
  {
    slug: 'recompras-acciones-vs-dividendos',
    tag: 'Estrategia',
    date: '31 jul 2026',
    readTime: '9 min',
    title: 'Recompras de acciones vs dividendos: qué gana el accionista con cada una',
    excerpt:
      'Las recompras difieren el IRPF y suben tu parte del pastel; los dividendos son renta que llega sola. Cuándo un buyback crea valor, cómo detectar los que destruyen y por qué el shareholder yield mide mejor que el yield a secas.',
    Image: ImgRecomprasVsDividendos,
  },
  {
    slug: 'fiscalidad-opciones-irpf-espana',
    tag: 'Fiscalidad',
    date: '30 jul 2026',
    readTime: '10 min',
    title: 'Fiscalidad de las opciones en el IRPF: cómo tributan las primas de puts y calls',
    excerpt:
      'Las primas de opciones son ganancias patrimoniales sin retención, y se imputan al vencimiento, no al cobro. Qué pasa si te ejercitan, cómo tributa la covered call y dónde va todo en Renta Web.',
    Image: ImgFiscalidadOpciones,
  },
  {
    slug: 'traspaso-acciones-entre-brokers',
    tag: 'Brokers',
    date: '29 jul 2026',
    readTime: '9 min',
    title: 'Traspasar acciones entre brokers: cómo cambiar de casa sin pagar peaje a Hacienda',
    excerpt:
      'El traspaso de valores no tributa; vender y recomprar sí. Cómo se solicita, cuánto cuesta por posición, por qué tus precios de compra pueden no viajar con los títulos y qué descargar antes de mudarte.',
    Image: ImgTraspasoBrokers,
  },
  {
    slug: 'formulario-w8ben-guia-espana',
    tag: 'Fiscalidad',
    date: '28 jul 2026',
    readTime: '8 min',
    title: 'Formulario W-8BEN en España: baja la retención de dividendos USA del 30% al 15%',
    excerpt: 'El W-8BEN es el papel que te ahorra la mitad de la retención de tus acciones y ETFs estadounidenses. Qué es, cómo rellenarlo en tu broker, que caduca a los 3 años y qué hacer si ya cobraste al 30%.',
    Image: ImgW8ben,
  },
  {
    slug: 'que-pasa-si-quiebra-tu-broker',
    tag: 'Brokers',
    date: '26 jul 2026',
    readTime: '9 min',
    title: '¿Qué pasa con tus acciones si tu broker quiebra? FOGAIN y segregación',
    excerpt: 'Tus acciones no son del broker: están segregadas y no entran en la masa concursal. Cómo funcionan las cuentas ómnibus, qué cubre el FOGAIN (100.000 €) y por qué DEGIRO, Trade Republic e IBKR se rigen por esquemas de solo 20.000 €.',
    Image: ImgQuiebraBroker,
  },
  {
    slug: 'regla-chowder-seleccion-dividendos',
    tag: 'Estrategia',
    date: '24 jul 2026',
    readTime: '8 min',
    title: 'La regla de Chowder: el filtro que separa un buen dividendo de una trampa',
    excerpt: 'El número de Chowder suma yield y crecimiento del dividendo en una sola cifra para filtrar acciones DGI. Cómo se calcula, los umbrales de 12 y 8, y por qué descarta trampas de yield alto que el yield solo no ve.',
    Image: ImgReglaChowder,
  },
  {
    slug: 'heredar-acciones-irpf',
    tag: 'Fiscalidad',
    date: '24 jul 2026',
    readTime: '9 min',
    title: 'Heredar o donar acciones: la plusvalía del muerto y los errores que se pagan dos veces',
    excerpt: 'Heredar borra la ganancia acumulada en IRPF; donar la hace tributar dos veces. Coste de adquisición, pactos sucesorios, FIFO con lotes heredados y qué documentar el día de la herencia.',
    Image: ImgHeredarAcciones,
  },
  {
    slug: 'dividendos-inflacion-poder-adquisitivo',
    tag: 'Estrategia',
    date: '23 jul 2026',
    readTime: '8 min',
    title: 'Dividendos e inflación: por qué tu poder adquisitivo importa más que el yield',
    excerpt: 'La inflación se come tu renta por dividendo aunque el yield suba. Cómo medir tu dividendo real, qué empresas aguantan la subida de precios y qué hacer para no perder poder adquisitivo.',
    Image: ImgDividendosInflacion,
  },
  {
    slug: 'tipos-interes-cartera-dividendos',
    tag: 'Estrategia',
    date: '22 jul 2026',
    readTime: '11 min',
    title: 'Tipos de interés y tu cartera de dividendos: qué hacer cuando el BCE mueve el precio del dinero',
    excerpt: 'El BCE subió tipos en junio de 2026 y el mercado descuenta más subidas. Te explicamos por qué eso mueve tus bancos, utilities y SOCIMIs, y qué tocar en tu cartera de dividendos.',
    Image: ImgTiposInteres,
  },
  {
    slug: 'dividend-aristocrats-europa-espana-2026',
    tag: 'Estrategia',
    date: '22 jul 2026',
    readTime: '11 min',
    title: 'Dividend Aristocrats en Europa y España: las acciones que suben el dividendo cada año',
    excerpt: 'Qué son los Dividend Aristocrats en Europa y España, qué empresas españolas entran en el índice S&P Europe 350 Dividend Aristocrats y cómo invertir en ellos desde España sin complicarte la fiscalidad.',
    Image: ImgAristocratsEuropa,
  },
  {
    slug: 'plan-ahorro-largo-plazo-pea',
    tag: 'Fiscalidad',
    date: '21 jul 2026',
    readTime: '9 min',
    title: 'Plan de Ahorro a Largo Plazo (PEA): dividendos al 0% de IRPF si aguantas 5 años',
    excerpt: 'Cómo funciona el PEA en España: exención del 0% en el IRPF para dividendos y plusvalías si mantienes el plan 5 años, el límite de 5.000€ al año y cómo declararlo en la Renta.',
    Image: ImgPea,
  },
  {
    slug: 'rebalanceo-cartera-dividendos',
    tag: 'Estrategia',
    date: '16 jul 2026',
    readTime: '7 min',
    title: 'Rebalancear tu cartera de dividendos sin disparar a Hacienda',
    excerpt: 'Cómo corregir la deriva de tu cartera de dividendos con bandas de tolerancia y dinero nuevo, sin pagar más IRPF del necesario por vender.',
    Image: ImgRebalanceo,
  },
  {
    slug: 'impuesto-patrimonio-inversores-espana',
    tag: 'Fiscal',
    date: '15 jul 2026',
    readTime: '12 min',
    title: 'Impuesto de Patrimonio 2026 para inversores: lo que pagas por tu cartera (y cómo minimizarlo)',
    excerpt: 'Guía práctica del Impuesto de Patrimonio para inversores en España: mínimo exento, valoración de acciones, fondos y ETFs, diferencias por Comunidad Autónoma, cómo declarar tu cartera en el Modelo 714 y estrategias legales para reducir lo que pagas.',
    Image: ImgImpuestoPatrimonio,
  },
  {
    slug: 'analisis-sectorial-dividendos-espana-2026',
    tag: 'Estrategia',
    date: '13 jul 2026',
    readTime: '12 min',
    title: 'Dónde invertir para dividendos en 2026: análisis sectorial completo',
    excerpt: 'La banca ya no es la reina del dividendo español. 26.399 M€ pagados en el primer semestre de 2026, pero el dinero está fluyendo hacia energía, utilities e infraestructuras. Análisis sectorial con datos reales y una propuesta práctica de asignación.',
    Image: ImgAnalisisSectorial,
  },
  {
    slug: 'mejores-etfs-dividendos-espana-2026',
    tag: 'Estrategia',
    date: '11 jul 2026',
    readTime: '13 min',
    title: 'Los mejores ETFs de dividendos para invertir desde España en 2026',
    excerpt: 'Guía práctica de los mejores ETFs de dividendos disponibles para inversores españoles: VHYL, FUSD, IQQY, SPDR Euro Dividend Aristocrats. TERs, yields, domicilios, fiscalidad y cómo elegir según tu perfil.',
    Image: ImgMejoresEtfs,
  },
  {
    slug: 'dividendos-hacienda-foral-navarra-euskadi',
    tag: 'Fiscal',
    date: '10 jul 2026',
    readTime: '13 min',
    title: 'Dividendos en Navarra y País Vasco: qué cambia con Hacienda Foral',
    excerpt: 'Cómo tributan los dividendos en Navarra y el País Vasco. Diferencias con el régimen común, tipos aplicables y el impacto en tu cartera.',
    Image: ImgDividendosHaciendaForal,
  },
{
    slug: 'opciones-ingresos-extra-dividendos',
    tag: 'Estrategia',
    date: '9 jul 2026',
    readTime: '12 min',
    title: 'Opciones para inversores de dividendos: ingresos extra con covered calls',
    excerpt: 'Cómo usar covered calls y cash-secured puts para generar ingresos adicionales sobre tu cartera de dividendos. Fiscalidad IRPF incluida.',
    Image: ImgOpcionesIngresos,
  },
  {
    slug: 'vivir-de-dividendos-20250707',
    tag: 'Estrategia',
    date: '7 jul 2026',
    readTime: '9 min',
    title: 'Vivir de los dividendos en España: el capital necesario y la realidad fiscal',
    excerpt: 'Cuánto capital necesitas para generar 2.000€ netos al mes y qué impacto tiene Hacienda en tu cartera. DGI, High Yield y CEFs comparados con números reales.',
    Image: ImgVivirDividendos,
  },
  {
    slug: 'metodo-dgi-construir-cartera-dividendos-20250705',
    tag: 'Estrategia',
    date: '5 jul 2025',
    readTime: '7 min',
    title: 'Cómo construir una cartera de dividendos desde cero: El método DGI',
    excerpt: 'Guía paso a paso para montar tu cartera de Dividend Growth Investing. Criterios de selección, métricas de seguridad y errores que te costarán dinero.',
    Image: ImgMetodoDgi,
  },
  {
    slug: 'seguridad-dividendo-metricas',
    tag: 'Métricas',
    date: '4 jul 2026',
    readTime: '13 min',
    title: 'Cómo analizar la seguridad del dividendo: las métricas que te alertan antes del recorte',
    excerpt: 'Aprende a evaluar si un dividendo es sostenible antes de que la empresa lo recorte. Payout ratio, free cash flow, cobertura y las señales de alerta que los inversores pasan por alto.',
    Image: ImgSeguridadDividendo,
  },
  {
    slug: 'total-return-vs-dividend-yield',
    tag: 'Métricas',
    date: '3 jul 2026',
    readTime: '11 min',
    title: 'Total return vs dividend yield: por qué el yield no es tu rentabilidad real',
    excerpt: 'El dividend yield es solo una parte de tu rentabilidad. Aprende a calcular el total return y por qué ignorar la revalorización te está costando dinero.',
    Image: ImgTotalReturn,
  },
  {
    slug: 'broker-dividendos-espana-2025',
    tag: 'Estrategia',
    date: '1 jul 2026',
    readTime: '10 min',
    title: 'Mejor broker para cobrar dividendos en España (2025)',
    excerpt: 'Comparativa real de brokers para inversores en dividendos: TR, DEGIRO, IBKR e ING. Retenciones, informes fiscales y qué hacer con Hacienda.',
    Image: ImgBroker,
  },
  {
    slug: 'trampas-dividendo-yield-insostenible',
    tag: 'Estrategia',
    date: '1 jul 2026',
    readTime: '13 min',
    title: 'Trampas del dividendo: cómo detectar un yield insostenible antes de que sea tarde',
    excerpt: 'Una rentabilidad por dividendo del 12% suena demasiado bien porque suele serlo. Guía práctica para identificar dividendos insostenibles en el mercado español con ejemplos reales y métricas clave.',
    Image: ImgTrampasDividendo,
  },
  {
    slug: 'planificacion-fiscal-fin-ano',
    tag: 'Fiscal',
    date: '29 jun 2026',
    readTime: '12 min',
    title: 'Planificación fiscal de fin de año para el inversor en dividendos: la guía que te ahorra dinero antes del 31 de diciembre',
    excerpt: 'Guía práctica para reducir tu factura fiscal antes del cierre del ejercicio: cuándo vender con pérdida, cómo manejar los tramos del ahorro, la regla de los 2 meses y un checklist de 7 pasos para diciembre.',
    Image: ImgPlanificacionFiscalFinAno,
  },
  {
    slug: 'retencion-19-vs-tributacion-real-irpf',
    tag: 'Fiscal',
    date: '28 jun 2026',
    readTime: '11 min',
    title: 'La retención del 19% de los dividendos no es lo que pagas realmente',
    excerpt: 'Tu broker te retiene el 19% cuando cobras dividendos, pero ese no es tu impuesto real. Si tu base del ahorro supera los 6.000 €, acabas pagando hasta un 28%. Te explico la diferencia con ejemplos prácticos.',
    Image: ImgRetencion19,
  },
  {
    slug: 'dividendos-individuales-vs-etf-acumulacion-fiscal',
    tag: 'Estrategia',
    date: '27 jun 2026',
    readTime: '14 min',
    title: 'Acciones de dividendos vs ETFs de acumulación: la cuenta que nadie te hace',
    excerpt: 'Comparativa fiscal real entre una cartera DGI de acciones individuales y un ETF de acumulación en España. El tax drag a 20 años, cuánto pierdes por el camino y qué te conviene según tu perfil.',
    Image: ImgDividendosVsEtf,
  },
  {
    slug: 'derechos-suscripcion-preferente-irpf',
    tag: 'Fiscal',
    date: '26 jun 2026',
    readTime: '13 min',
    title: 'Derechos de suscripción preferente en el IRPF: qué hacer y cómo tributa cada opción',
    excerpt: 'Guía práctica sobre los derechos de suscripción preferente: las tres opciones (suscribir, vender en mercado, vender a la empresa), cómo tributa cada una en el IRPF, el cambio de 2017 y ejemplos con números reales.',
    Image: ImgDerechosSuscripcion,
  },
  {
    slug: 'gastos-deducibles-inversion-irpf',
    tag: 'Fiscal',
    date: '25 jun 2026',
    readTime: '14 min',
    title: 'Gastos deducibles del inversor en el IRPF: qué comisiones y costes puedes restar',
    excerpt: 'Guía práctica sobre qué gastos de inversión son deducibles en el IRPF: comisiones de custodia, administración de valores, cánones de bolsa, gastos de divisa y cómo incluirlos en la declaración.',
    Image: ImgGastosDeducibles,
  },
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
    slug: 'reits-extranjeros-irpf-espana',
    tag: 'Fiscal',
    date: '24 jun 2026',
    readTime: '15 min',
    title: 'Dividendos de REITs extranjeros en el IRPF: guía fiscal para inversores desde España',
    excerpt: 'Cómo tributan los dividendos de REITs extranjeros (Realty Income, Prologis, Vonovia) en el IRPF: retenciones por país, convenios de doble imposición, casillas 029 y 0588, y ejemplos con números reales.',
    Image: ImgReitsExtranjeros,
  },
  {
    slug: 'prima-emision-reduccion-capital-irpf',
    tag: 'Fiscal',
    date: '22 jun 2026',
    readTime: '14 min',
    title: 'Prima de emisión y reducción de capital en el IRPF: qué tributa y qué no cuando la empresa devuelve tu dinero',
    excerpt: 'La prima de emisión y la reducción de capital no tributan como dividendo en la mayoría de casos. Guía práctica con ejemplos, la DGT V0215-26 de febrero 2026 y cómo afecta a tu cartera de dividendos.',
    Image: ImgPrimaEmision,
  },
  {
    slug: 'calendario-dividendos-irpf',
    tag: 'Estrategia',
    date: '20 jun 2026',
    readTime: '14 min',
    title: 'Calendario de dividendos: cómo planificar tus ingresos mes a mes',
    excerpt: 'Guía completa sobre el calendario de dividendos: fecha ex-dividendo, fecha de pago, cómo planificar ingresos mensuales con cartera mixta España-EE.UU. y errores frecuentes al cobrar.',
    Image: ImgCalendarioDividendos,
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
