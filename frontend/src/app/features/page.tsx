import { PublicNav } from '@/components/PublicNav';
import { PublicFooter } from '@/components/PublicFooter';
import styles from './features.module.css';

function IconPortfolio() {
  return (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="var(--fv-ochre)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="2" y="3" width="20" height="14" rx="2"/>
      <path d="M8 21h8M12 17v4"/>
      <path d="M6 8h2v5H6zM11 6h2v7h-2zM16 10h2v3h-2z"/>
    </svg>
  );
}

function IconCalendar() {
  return (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="var(--fv-ochre)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="3" y="4" width="18" height="18" rx="2"/>
      <path d="M16 2v4M8 2v4M3 10h18"/>
      <circle cx="8" cy="15" r="1" fill="var(--fv-ochre)"/>
      <circle cx="12" cy="15" r="1" fill="var(--fv-ochre)"/>
      <circle cx="16" cy="15" r="1" fill="var(--fv-ochre)"/>
    </svg>
  );
}

function IconImport() {
  return (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="var(--fv-ochre)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
      <polyline points="7 10 12 15 17 10"/>
      <line x1="12" y1="15" x2="12" y2="3"/>
    </svg>
  );
}

function IconTax() {
  return (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="var(--fv-ochre)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
      <polyline points="14 2 14 8 20 8"/>
      <line x1="9" y1="13" x2="15" y2="13"/>
      <line x1="9" y1="17" x2="15" y2="17"/>
      <line x1="9" y1="9" x2="11" y2="9"/>
    </svg>
  );
}

function IconMetrics() {
  return (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="var(--fv-ochre)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/>
      <polyline points="16 7 22 7 22 13"/>
    </svg>
  );
}

function IconCurrency() {
  return (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="var(--fv-ochre)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="10"/>
      <path d="M15 9.354A4 4 0 1 0 12 16v-4"/>
      <line x1="8" y1="12" x2="16" y2="12"/>
    </svg>
  );
}

type BarHClass = 'barH32' | 'barH48' | 'barH62' | 'barH80' | 'barH100' | 'barH118';
type BarEntry = { year: string; hClass: BarHClass; amount: string };

const BARS: BarEntry[] = [
  { year: '2020', hClass: 'barH32',  amount: '1.240 €' },
  { year: '2021', hClass: 'barH48',  amount: '1.870 €' },
  { year: '2022', hClass: 'barH62',  amount: '2.410 €' },
  { year: '2023', hClass: 'barH80',  amount: '3.120 €' },
  { year: '2024', hClass: 'barH100', amount: '3.890 €' },
  { year: '2025', hClass: 'barH118', amount: '4.620 €' },
];

const CHART_META = [
  { label: 'Yield on cost', value: '6.2%' },
  { label: 'CAGR dividendos', value: '+24.1%' },
  { label: 'Próximo cobro', value: '14 may' },
];

function DividendChart() {
  return (
    <div className={styles.chart}>
      <p className={styles.chartLabel}>Dividendos cobrados por año</p>
      <p className={styles.chartTitle}>
        4.620 <span className={styles.chartTitleMuted}>€ en 2025</span>
      </p>
      <div className={styles.bars}>
        {BARS.map(({ year, hClass, amount }) => (
          <div key={year} className={styles.barCol}>
            <div className={`${styles.bar} ${styles[hClass]} ${year === '2025' ? styles.barActive : ''}`}>
              {year === '2025' && <span className={styles.barLabel}>{amount}</span>}
            </div>
            <span className={styles.barYear}>{year}</span>
          </div>
        ))}
      </div>
      <div className={styles.chartMeta}>
        {CHART_META.map(({ label, value }) => (
          <div key={label} className={styles.chartMetaItem}>
            <p>{label}</p>
            <p>{value}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

const FEATURES = [
  { Icon: IconPortfolio, title: 'Cartera unificada', desc: 'Importa posiciones de DEGIRO, IBKR y Trade Republic. Todas tus inversiones, sus dividendos y su evolución en un único panel.' },
  { Icon: IconCalendar, title: 'Calendario de pagos', desc: 'Visualiza cada cobro futuro con fecha ex-dividendo, fecha de pago e importe estimado en euros. Nunca más te pillará por sorpresa.' },
  { Icon: IconImport, title: 'Importación automática', desc: 'Sube el Tax Report de Trade Republic, los CSV de DEGIRO o los Activity Statements de IBKR. Procesado y cruzado en segundos.' },
  { Icon: IconTax, title: 'Motor fiscal IRPF', desc: 'FIFO cross-broker según normativa española, casillas del Modelo 100 y 714 pre-calculadas y validadas contra los datos de Trade Republic.' },
  { Icon: IconMetrics, title: 'Métricas avanzadas', desc: 'Yield on cost, yield on price, rentabilidad total, CAGR de dividendos y comparativa anual. Métricas que los grandes inversores siguen.' },
  { Icon: IconCurrency, title: 'Multi-divisa', desc: 'Conversión automática EUR/USD/GBP con tipo de cambio histórico. Tus retenciones en origen también quedan reflejadas con precisión.' },
];

const STEPS = [
  { n: '01', title: 'Importa tus datos', desc: 'Sube el Tax Report PDF de Trade Republic, el CSV de DEGIRO o el Activity Statement de IBKR. Sin configuración manual.', detail: 'Compatible con TR, DEGIRO e IBKR' },
  { n: '02', title: 'FinView lo calcula todo', desc: 'Cruce de datos entre brokers, cálculo FIFO según normativa española, conversión de divisas y agrupación de dividendos por año y ticker.', detail: 'Procesado en menos de 10 segundos' },
  { n: '03', title: 'Declara con confianza', desc: 'Obtén tus casillas del Modelo 100 y 714 listas para copiar. Descarga un resumen en CSV para tu asesor o para tu propio archivo.', detail: 'Casillas 27, 29, 332, 337 y más' },
];

export default function FeaturesPage() {
  return (
    <div className={styles.page}>
      <PublicNav />

      {/* ── Hero ── */}
      <section className={styles.hero}>
        <span className={styles.eyebrow}>
          <span className={styles.dot} />
          Funcionalidades
        </span>
        <h1 className={styles.h1}>
          La herramienta que los inversores de dividendos en España{' '}
          <em className={styles.em}>necesitaban</em>
        </h1>
        <p className={styles.lead}>
          Desde la importación automática de tus brokers hasta las casillas del IRPF,
          FinView cubre todo el ciclo de tu inversión en dividendos.
        </p>
        <a href="/register" className={styles.ctaPrimary}>Empezar gratis →</a>
      </section>

      {/* ── Chart ── */}
      <section className={styles.chartWrap}>
        <div className={styles.chartInner}>
          <DividendChart />
        </div>
      </section>

      {/* ── Features grid ── */}
      <section className={styles.featuresBg}>
        <div className={styles.wrap}>
          <h2 className={styles.h2}>Todo lo que necesitas, nada de lo que no</h2>
          <div className={styles.featuresGrid}>
            {FEATURES.map(({ Icon, title, desc }) => (
              <div key={title} className={styles.featureCard}>
                <div className={styles.featureIcon}><Icon /></div>
                <h3 className={styles.featureTitle}>{title}</h3>
                <p className={styles.featureDesc}>{desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── How it works ── */}
      <section className={styles.steps}>
        <div className={styles.stepsHeader}>
          <h2 className={styles.h2}>Tres pasos, cero complicaciones</h2>
          <p className={styles.stepsSubtitle}>
            De tus archivos de broker a tus casillas IRPF en menos de un minuto.
          </p>
        </div>
        <div className={styles.stepsGrid}>
          {STEPS.map(({ n, title, desc, detail }, i) => (
            <div key={n} className={`${styles.stepItem} ${i < 2 ? styles.stepBorder : ''}`}>
              <span className={styles.stepNum}>{n}</span>
              <h3 className={styles.stepTitle}>{title}</h3>
              <p className={styles.stepDesc}>{desc}</p>
              <span className={styles.stepBadge}>{detail}</span>
            </div>
          ))}
        </div>
      </section>

      {/* ── Brokers ── */}
      <section className={styles.brokersBg}>
        <div className={styles.brokersInner}>
          <p className={styles.brokersLabel}>Compatible con tus brokers</p>
          <div className={styles.brokerList}>
            {['Trade Republic', 'DEGIRO', 'IBKR'].map(broker => (
              <span key={broker} className={styles.brokerName}>{broker}</span>
            ))}
          </div>
        </div>
      </section>

      {/* ── CTA ── */}
      <section className={styles.ctaSection}>
        <h2 className={styles.h2}>
          Empieza gratis hoy.{' '}
          <em className={styles.em}>Sin tarjeta.</em>
        </h2>
        <p className={styles.lead}>
          Importa tus datos y ten tus casillas IRPF listas en minutos.
        </p>
        <div className={styles.ctaLinks}>
          <a href="/register" className={styles.ctaPrimary}>Crear cuenta gratis →</a>
          <a href="/pricing" className={styles.ctaSecondary}>Ver precios</a>
        </div>
      </section>

      <PublicFooter />
    </div>
  );
}
