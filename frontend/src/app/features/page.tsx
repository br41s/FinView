import { PublicNav } from '@/components/PublicNav';
import { PublicFooter } from '@/components/PublicFooter';

const s = {
  page: { background: 'var(--fv-paper)', color: 'var(--fv-ink)', minHeight: '100vh', fontFamily: 'var(--fv-font-sans)' } as React.CSSProperties,
  wrap: { maxWidth: 1320, margin: '0 auto', padding: '0 32px' } as React.CSSProperties,
};

// ── Inline SVG icons ───────────────────────────────────────────────────────────

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

// ── Mini dividend bar chart ─────────────────────────────────────────────────────

function DividendChart() {
  const bars = [
    { year: '2020', h: 32, amount: '1.240 €' },
    { year: '2021', h: 48, amount: '1.870 €' },
    { year: '2022', h: 62, amount: '2.410 €' },
    { year: '2023', h: 80, amount: '3.120 €' },
    { year: '2024', h: 100, amount: '3.890 €' },
    { year: '2025', h: 118, amount: '4.620 €' },
  ];

  return (
    <div style={{
      background: 'var(--fv-paper)', border: '1px solid var(--fv-ink-10)',
      borderRadius: 16, padding: '32px 40px',
      boxShadow: 'var(--fv-shadow-lg)',
    }}>
      <p style={{ fontSize: 11, fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.14em', color: 'var(--fv-ink-40)', marginBottom: 6 }}>
        Dividendos cobrados por año
      </p>
      <p style={{ fontFamily: 'var(--fv-font-display)', fontSize: 32, color: 'var(--fv-ink)', margin: '0 0 32px', lineHeight: 1 }}>
        4.620 <span style={{ fontSize: 20, color: 'var(--fv-ink-60)' }}>€ en 2025</span>
      </p>
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 12, height: 140 }}>
        {bars.map(({ year, h, amount }) => (
          <div key={year} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }}>
            <div style={{
              width: '100%', height: h,
              background: year === '2025' ? 'var(--fv-ochre)' : 'var(--fv-ochre-ghost)',
              borderRadius: '4px 4px 0 0',
              position: 'relative',
            }}>
              {year === '2025' && (
                <span style={{
                  position: 'absolute', top: -24, left: '50%', transform: 'translateX(-50%)',
                  fontSize: 11, fontWeight: 600, color: 'var(--fv-ochre)', whiteSpace: 'nowrap',
                }}>
                  {amount}
                </span>
              )}
            </div>
            <span style={{ fontSize: 11, color: 'var(--fv-ink-40)' }}>{year}</span>
          </div>
        ))}
      </div>
      <div style={{ display: 'flex', gap: 24, marginTop: 24, paddingTop: 20, borderTop: '1px solid var(--fv-ink-10)' }}>
        {[
          { label: 'Yield on cost', value: '6.2%' },
          { label: 'CAGR dividendos', value: '+24.1%' },
          { label: 'Próximo cobro', value: '14 may' },
        ].map(({ label, value }) => (
          <div key={label}>
            <p style={{ fontSize: 11, color: 'var(--fv-ink-40)', margin: 0 }}>{label}</p>
            <p style={{ fontSize: 15, fontWeight: 600, color: 'var(--fv-ink)', margin: '2px 0 0' }}>{value}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Data ────────────────────────────────────────────────────────────────────────

const features = [
  {
    Icon: IconPortfolio,
    title: 'Cartera unificada',
    desc: 'Importa posiciones de DEGIRO, IBKR y Trade Republic. Todas tus inversiones, sus dividendos y su evolución en un único panel.',
  },
  {
    Icon: IconCalendar,
    title: 'Calendario de pagos',
    desc: 'Visualiza cada cobro futuro con fecha ex-dividendo, fecha de pago e importe estimado en euros. Nunca más te pillará por sorpresa.',
  },
  {
    Icon: IconImport,
    title: 'Importación automática',
    desc: 'Sube el Tax Report de Trade Republic, los CSV de DEGIRO o los Activity Statements de IBKR. Procesado y cruzado en segundos.',
  },
  {
    Icon: IconTax,
    title: 'Motor fiscal IRPF',
    desc: 'FIFO cross-broker según normativa española, casillas del Modelo 100 y 714 pre-calculadas y validadas contra los datos de Trade Republic.',
  },
  {
    Icon: IconMetrics,
    title: 'Métricas avanzadas',
    desc: 'Yield on cost, yield on price, rentabilidad total, CAGR de dividendos y comparativa anual. Métricas que los grandes inversores siguen.',
  },
  {
    Icon: IconCurrency,
    title: 'Multi-divisa',
    desc: 'Conversión automática EUR/USD/GBP con tipo de cambio histórico. Tus retenciones en origen también quedan reflejadas con precisión.',
  },
];

const steps = [
  {
    n: '01',
    title: 'Importa tus datos',
    desc: 'Sube el Tax Report PDF de Trade Republic, el CSV de transacciones de DEGIRO o el Activity Statement de IBKR. Sin configuración manual.',
    detail: 'Compatible con TR, DEGIRO e IBKR',
  },
  {
    n: '02',
    title: 'FinView lo calcula todo',
    desc: 'Cruce de datos entre brokers, cálculo FIFO según normativa española, conversión de divisas y agrupación de dividendos por año y ticker.',
    detail: 'Procesado en menos de 10 segundos',
  },
  {
    n: '03',
    title: 'Declara con confianza',
    desc: 'Obtén tus casillas del Modelo 100 y 714 listas para copiar. Descarga un resumen en CSV para tu asesor o para tu propio archivo.',
    detail: 'Casillas 27, 29, 332, 337 y más',
  },
];

// ── Page ────────────────────────────────────────────────────────────────────────

export default function FeaturesPage() {
  return (
    <div style={s.page}>
      <PublicNav />

      {/* ── Hero ── */}
      <section style={{ ...s.wrap, padding: '96px 32px 80px', textAlign: 'center' }}>
        <span style={{
          display: 'inline-flex', alignItems: 'center', gap: 8,
          fontSize: 11, fontWeight: 500, textTransform: 'uppercase',
          letterSpacing: '0.18em', color: 'var(--fv-ink-40)', marginBottom: 24,
        }}>
          <span style={{ width: 6, height: 6, borderRadius: 999, background: 'var(--fv-ochre)', display: 'inline-block' }} />
          Funcionalidades
        </span>
        <h1 style={{
          fontFamily: 'var(--fv-font-display)', fontWeight: 400,
          fontSize: 'clamp(2.6rem, 6vw, 5rem)', lineHeight: 1.05,
          letterSpacing: '-0.02em', color: 'var(--fv-ink)',
          maxWidth: '18ch', margin: '0 auto 24px',
        }}>
          La herramienta que los inversores de dividendos en España{' '}
          <em style={{ color: 'var(--fv-ochre)', fontStyle: 'italic' }}>necesitaban</em>
        </h1>
        <p style={{ fontSize: 18, lineHeight: 1.6, color: 'var(--fv-ink-70)', maxWidth: 520, margin: '0 auto 48px' }}>
          Desde la importación automática de tus brokers hasta las casillas del IRPF,
          FinView cubre todo el ciclo de tu inversión en dividendos.
        </p>
        <a href="/register" style={{
          background: 'var(--fv-ochre)', color: 'var(--fv-paper)',
          borderRadius: 'var(--fv-r-pill)', padding: '14px 28px',
          fontSize: 15, fontWeight: 500, textDecoration: 'none',
          display: 'inline-block',
        }}>
          Empezar gratis →
        </a>
      </section>

      {/* ── Dashboard preview ── */}
      <section style={{ ...s.wrap, padding: '0 32px 96px' }}>
        <div style={{ maxWidth: 680, margin: '0 auto' }}>
          <DividendChart />
        </div>
      </section>

      {/* ── Features grid ── */}
      <section style={{ background: 'var(--fv-ink-05)', padding: '96px 0' }}>
        <div style={s.wrap}>
          <h2 style={{
            fontFamily: 'var(--fv-font-display)', fontWeight: 400,
            fontSize: 'clamp(2rem, 4vw, 3rem)', letterSpacing: '-0.02em',
            color: 'var(--fv-ink)', marginBottom: 56, textAlign: 'center',
          }}>
            Todo lo que necesitas, nada de lo que no
          </h2>
          <div style={{
            display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 24,
          }}>
            {features.map(({ Icon, title, desc }) => (
              <div key={title} style={{
                background: 'var(--fv-paper)', border: '1px solid var(--fv-ink-10)',
                borderRadius: 16, padding: '32px',
                transition: 'box-shadow 200ms',
              }}>
                <div style={{
                  width: 52, height: 52, borderRadius: 12,
                  background: 'var(--fv-ochre-ghost)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  marginBottom: 20,
                }}>
                  <Icon />
                </div>
                <h3 style={{ fontSize: 17, fontWeight: 600, color: 'var(--fv-ink)', margin: '0 0 10px' }}>
                  {title}
                </h3>
                <p style={{ fontSize: 14, lineHeight: 1.6, color: 'var(--fv-ink-70)', margin: 0 }}>
                  {desc}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── How it works ── */}
      <section style={{ ...s.wrap, padding: '96px 32px' }}>
        <div style={{ textAlign: 'center', marginBottom: 64 }}>
          <h2 style={{
            fontFamily: 'var(--fv-font-display)', fontWeight: 400,
            fontSize: 'clamp(2rem, 4vw, 3rem)', letterSpacing: '-0.02em',
            color: 'var(--fv-ink)', margin: '0 0 16px',
          }}>
            Tres pasos, cero complicaciones
          </h2>
          <p style={{ fontSize: 17, color: 'var(--fv-ink-70)', maxWidth: 440, margin: '0 auto' }}>
            De tus archivos de broker a tus casillas IRPF en menos de un minuto.
          </p>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 0 }}>
          {steps.map(({ n, title, desc, detail }, i) => (
            <div key={n} style={{
              padding: '40px 36px',
              borderRight: i < 2 ? '1px solid var(--fv-ink-10)' : 'none',
              position: 'relative',
            }}>
              <span style={{
                fontFamily: 'var(--fv-font-display)', fontSize: 64, fontWeight: 400,
                color: 'var(--fv-ink-05)', lineHeight: 1, display: 'block',
                marginBottom: -8,
              }}>
                {n}
              </span>
              <h3 style={{ fontSize: 20, fontWeight: 600, color: 'var(--fv-ink)', margin: '0 0 12px' }}>
                {title}
              </h3>
              <p style={{ fontSize: 14, lineHeight: 1.7, color: 'var(--fv-ink-70)', margin: '0 0 16px' }}>
                {desc}
              </p>
              <span style={{
                fontSize: 12, fontWeight: 500, color: 'var(--fv-ochre)',
                background: 'var(--fv-ochre-ghost)', borderRadius: 'var(--fv-r-pill)',
                padding: '4px 12px', display: 'inline-block',
              }}>
                {detail}
              </span>
            </div>
          ))}
        </div>
      </section>

      {/* ── Brokers ── */}
      <section style={{ background: 'var(--fv-ink-05)', padding: '64px 0' }}>
        <div style={{ ...s.wrap, textAlign: 'center' }}>
          <p style={{ fontSize: 12, fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.16em', color: 'var(--fv-ink-40)', marginBottom: 32 }}>
            Compatible con tus brokers
          </p>
          <div style={{ display: 'flex', gap: 48, justifyContent: 'center', alignItems: 'center', flexWrap: 'wrap' }}>
            {['Trade Republic', 'DEGIRO', 'IBKR'].map(broker => (
              <span key={broker} style={{
                fontFamily: 'var(--fv-font-display)', fontSize: 22,
                color: 'var(--fv-ink-60)', letterSpacing: '-0.01em',
              }}>
                {broker}
              </span>
            ))}
          </div>
        </div>
      </section>

      {/* ── CTA ── */}
      <section style={{ ...s.wrap, padding: '96px 32px', textAlign: 'center' }}>
        <h2 style={{
          fontFamily: 'var(--fv-font-display)', fontWeight: 400,
          fontSize: 'clamp(2rem, 4vw, 3.2rem)', letterSpacing: '-0.02em',
          color: 'var(--fv-ink)', margin: '0 0 16px',
        }}>
          Empieza gratis hoy.{' '}
          <em style={{ color: 'var(--fv-ochre)', fontStyle: 'italic' }}>Sin tarjeta.</em>
        </h2>
        <p style={{ fontSize: 17, color: 'var(--fv-ink-70)', margin: '0 0 40px' }}>
          Importa tus datos y ten tus casillas IRPF listas en minutos.
        </p>
        <div style={{ display: 'flex', gap: 16, justifyContent: 'center', alignItems: 'center' }}>
          <a href="/register" style={{
            background: 'var(--fv-ochre)', color: 'var(--fv-paper)',
            borderRadius: 'var(--fv-r-pill)', padding: '14px 28px',
            fontSize: 15, fontWeight: 500, textDecoration: 'none',
            display: 'inline-block',
          }}>
            Crear cuenta gratis →
          </a>
          <a href="/pricing" style={{
            color: 'var(--fv-ink-70)', fontSize: 15, textDecoration: 'none',
          }}>
            Ver precios
          </a>
        </div>
      </section>

      <PublicFooter />
    </div>
  );
}
