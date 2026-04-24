import { PublicNav } from '@/components/PublicNav';
import { PublicFooter } from '@/components/PublicFooter';

// ── Data ────────────────────────────────────────────────────────────────────────

const POSTS = [
  {
    slug: 'estrategia-dgi',
    tag: 'Estrategia',
    date: '10 abr 2025',
    readTime: '5 min',
    title: 'La estrategia DGI: cómo invertir para vivir de dividendos',
    excerpt:
      'Dividend Growth Investing no es comprar las acciones con mayor rentabilidad por dividendo. Es encontrar empresas que llevan décadas aumentando su pago año tras año, y dejar que el tiempo haga el resto.',
    image: (
      <div style={{
        height: 200, borderRadius: '12px 12px 0 0',
        background: 'linear-gradient(135deg, var(--fv-ochre-ghost) 0%, rgba(154,107,31,0.2) 100%)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        overflow: 'hidden',
      }}>
        <svg viewBox="0 0 200 120" width="200" height="120" fill="none" aria-hidden="true">
          {[20, 40, 60, 80, 100, 120, 140, 160, 180].map((x, i) => (
            <rect key={x} x={x - 12} y={110 - [20,32,44,38,56,70,62,84,96][i]} width="20" height={[20,32,44,38,56,70,62,84,96][i]}
              fill={i === 8 ? 'var(--fv-ochre)' : 'rgba(154,107,31,0.25)'} rx="3"/>
          ))}
          <polyline
            points="8,90 28,78 48,66 68,72 88,54 108,40 128,48 148,26 168,14 188,4"
            stroke="var(--fv-ochre)" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round"
          />
        </svg>
      </div>
    ),
  },
  {
    slug: 'declarar-dividendos-espana',
    tag: 'Fiscal',
    date: '2 abr 2025',
    readTime: '7 min',
    title: 'Cómo declarar los dividendos en España: guía 2025',
    excerpt:
      'Cada dividendo que cobras tiene implicaciones fiscales en España. Te explicamos qué casillas del Modelo 100 debes rellenar, cómo funciona la doble imposición y qué retenciones puedes deducir.',
    image: (
      <div style={{
        height: 200, borderRadius: '12px 12px 0 0',
        background: 'linear-gradient(135deg, rgba(31,27,22,0.04) 0%, rgba(31,27,22,0.08) 100%)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        <svg viewBox="0 0 180 120" width="180" height="120" fill="none" aria-hidden="true">
          <rect x="20" y="10" width="140" height="100" rx="8" stroke="var(--fv-ink-30)" strokeWidth="1.5"/>
          <line x1="20" y1="32" x2="160" y2="32" stroke="var(--fv-ink-15)" strokeWidth="1"/>
          {[['Casilla 27', '1.529,64 €', 44], ['Casilla 29', '5.301,02 €', 60], ['Casilla 332', '297,40 €', 76], ['Casilla 337', '-2.155,11 €', 92]].map(([label, val, y]) => (
            <g key={String(y)}>
              <text x="30" y={Number(y)} fontSize="9" fill="var(--fv-ink-60)" fontFamily="system-ui">{label}</text>
              <text x="130" y={Number(y)} fontSize="9" fill="var(--fv-ink)" fontFamily="system-ui" textAnchor="end">{val}</text>
            </g>
          ))}
          <rect x="28" y="18" width="40" height="8" rx="2" fill="var(--fv-ochre-ghost)"/>
          <text x="48" y="25" fontSize="7" fill="var(--fv-ochre)" fontFamily="system-ui" textAnchor="middle">IRPF 2024</text>
        </svg>
      </div>
    ),
  },
  {
    slug: 'yield-on-cost',
    tag: 'Métricas',
    date: '15 mar 2025',
    readTime: '4 min',
    title: 'Yield on cost: la métrica que los grandes inversores de dividendos miden',
    excerpt:
      'El yield on price te dice lo que cobras hoy. El yield on cost te dice lo que cobras respecto a lo que pagaste. Con el tiempo, esta diferencia se convierte en la historia real de tu inversión.',
    image: (
      <div style={{
        height: 200, borderRadius: '12px 12px 0 0',
        background: 'linear-gradient(135deg, rgba(154,107,31,0.08) 0%, rgba(154,107,31,0.18) 100%)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 8,
      }}>
        <div style={{ display: 'flex', gap: 24, alignItems: 'flex-end' }}>
          {[
            { label: 'YOP', value: '3.1%', h: 60 },
            { label: 'YOC', value: '8.4%', h: 112 },
          ].map(({ label, value, h }) => (
            <div key={label} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }}>
              <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--fv-ochre)', fontFamily: 'system-ui' }}>{value}</span>
              <div style={{ width: 40, height: h, background: 'var(--fv-ochre)', borderRadius: '4px 4px 0 0', opacity: label === 'YOP' ? 0.35 : 1 }} />
              <span style={{ fontSize: 10, color: 'var(--fv-ink-60)', fontFamily: 'system-ui' }}>{label}</span>
            </div>
          ))}
        </div>
        <span style={{ fontSize: 10, color: 'var(--fv-ink-40)', fontFamily: 'system-ui' }}>Compra: 2018 · Hoy: 2025</span>
      </div>
    ),
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

// ── Icon ─────────────────────────────────────────────────────────────────────

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

// ── Page ────────────────────────────────────────────────────────────────────────

export default function BlogPage() {
  return (
    <div style={{ background: 'var(--fv-paper)', color: 'var(--fv-ink)', minHeight: '100vh', fontFamily: 'var(--fv-font-sans)' }}>
      <PublicNav />

      {/* ── Hero ── */}
      <section style={{ maxWidth: 1320, margin: '0 auto', padding: '80px 32px 64px', textAlign: 'center' }}>
        <span style={{
          display: 'inline-flex', alignItems: 'center', gap: 8,
          fontSize: 11, fontWeight: 500, textTransform: 'uppercase',
          letterSpacing: '0.18em', color: 'var(--fv-ink-40)', marginBottom: 24,
        }}>
          <span style={{ width: 6, height: 6, borderRadius: 999, background: 'var(--fv-ochre)', display: 'inline-block' }} />
          Más información
        </span>
        <h1 style={{
          fontFamily: 'var(--fv-font-display)', fontWeight: 400,
          fontSize: 'clamp(2.4rem, 5vw, 4.5rem)', lineHeight: 1.05,
          letterSpacing: '-0.02em', color: 'var(--fv-ink)', maxWidth: '18ch',
          margin: '0 auto 20px',
        }}>
          Aprende a invertir en{' '}
          <em style={{ color: 'var(--fv-ochre)', fontStyle: 'italic' }}>dividendos</em>
        </h1>
        <p style={{ fontSize: 18, lineHeight: 1.6, color: 'var(--fv-ink-70)', maxWidth: 480, margin: '0 auto' }}>
          Estrategia, fiscalidad y métricas para el inversor de largo plazo en España.
        </p>
      </section>

      {/* ── Blog posts ── */}
      <section style={{ maxWidth: 1100, margin: '0 auto', padding: '0 32px 96px' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 24 }}>
          {POSTS.map(({ slug, tag, date, readTime, title, excerpt, image }) => (
            <article key={slug} style={{
              background: 'var(--fv-paper)', border: '1px solid var(--fv-ink-10)',
              borderRadius: 16, overflow: 'hidden',
              display: 'flex', flexDirection: 'column',
              transition: 'box-shadow 200ms, transform 200ms',
            }}>
              {image}
              <div style={{ padding: '24px 28px 28px', flex: 1, display: 'flex', flexDirection: 'column' }}>
                <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 12 }}>
                  <span style={{
                    fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.1em',
                    color: 'var(--fv-ochre)', background: 'var(--fv-ochre-ghost)',
                    borderRadius: 999, padding: '3px 10px',
                  }}>
                    {tag}
                  </span>
                  <span style={{ fontSize: 12, color: 'var(--fv-ink-40)' }}>{date} · {readTime}</span>
                </div>
                <h2 style={{
                  fontFamily: 'var(--fv-font-display)', fontWeight: 400,
                  fontSize: 19, lineHeight: 1.3, letterSpacing: '-0.01em',
                  color: 'var(--fv-ink)', margin: '0 0 12px',
                }}>
                  {title}
                </h2>
                <p style={{ fontSize: 14, lineHeight: 1.7, color: 'var(--fv-ink-70)', margin: '0 0 20px', flex: 1 }}>
                  {excerpt}
                </p>
                <a href={`/blog/${slug}`} style={{
                  fontSize: 13, fontWeight: 500, color: 'var(--fv-ochre)',
                  textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: 4,
                }}>
                  Leer artículo →
                </a>
              </div>
            </article>
          ))}
        </div>
      </section>

      {/* ── Social feeds ── */}
      <section style={{ background: 'var(--fv-ink-05)', padding: '80px 0' }}>
        <div style={{ maxWidth: 1100, margin: '0 auto', padding: '0 32px' }}>
          <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 40 }}>
            <div>
              <h2 style={{
                fontFamily: 'var(--fv-font-display)', fontWeight: 400,
                fontSize: 'clamp(1.8rem, 3.5vw, 2.6rem)', letterSpacing: '-0.02em',
                color: 'var(--fv-ink)', margin: '0 0 8px',
              }}>
                En redes
              </h2>
              <p style={{ fontSize: 15, color: 'var(--fv-ink-60)', margin: 0 }}>
                Seguimiento diario de dividendos, tips fiscales y noticias del mercado.
              </p>
            </div>
            <a
              href="https://x.com/finviewapp"
              target="_blank"
              rel="noopener noreferrer"
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 8,
                background: 'var(--fv-ink)', color: 'var(--fv-paper)',
                borderRadius: 'var(--fv-r-pill)', padding: '10px 18px',
                fontSize: 13, fontWeight: 500, textDecoration: 'none',
                flexShrink: 0,
              }}
            >
              <XIcon /> Seguir en X
            </a>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 20 }}>
            {SOCIAL_POSTS.map(({ handle, name, time, content, likes, reposts }) => (
              <div key={content.slice(0, 20)} style={{
                background: 'var(--fv-paper)', border: '1px solid var(--fv-ink-10)',
                borderRadius: 16, padding: '24px',
              }}>
                {/* Header */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
                  <div style={{
                    width: 40, height: 40, borderRadius: 999,
                    background: 'var(--fv-ochre)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    flexShrink: 0,
                  }}>
                    <span style={{ fontSize: 14, fontWeight: 700, color: 'var(--fv-paper)', fontFamily: 'var(--fv-font-display)' }}>
                      F
                    </span>
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <p style={{ fontSize: 14, fontWeight: 600, color: 'var(--fv-ink)', margin: 0, lineHeight: 1.3 }}>{name}</p>
                    <p style={{ fontSize: 12, color: 'var(--fv-ink-40)', margin: 0 }}>{handle}</p>
                  </div>
                  <span style={{ color: 'var(--fv-ink-30)', flexShrink: 0 }}><XIcon /></span>
                </div>

                {/* Content */}
                <p style={{
                  fontSize: 14, lineHeight: 1.65, color: 'var(--fv-ink)',
                  margin: '0 0 16px', whiteSpace: 'pre-line',
                }}>
                  {content}
                </p>

                {/* Footer */}
                <div style={{ display: 'flex', gap: 20, borderTop: '1px solid var(--fv-ink-10)', paddingTop: 14 }}>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 13, color: 'var(--fv-ink-40)' }}>
                    <HeartIcon /> {likes}
                  </span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 13, color: 'var(--fv-ink-40)' }}>
                    <RepostIcon /> {reposts}
                  </span>
                  <span style={{ marginLeft: 'auto', fontSize: 12, color: 'var(--fv-ink-30)' }}>{time}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Newsletter CTA ── */}
      <section style={{ maxWidth: 1320, margin: '0 auto', padding: '80px 32px', textAlign: 'center' }}>
        <h2 style={{
          fontFamily: 'var(--fv-font-display)', fontWeight: 400,
          fontSize: 'clamp(1.8rem, 3.5vw, 2.8rem)', letterSpacing: '-0.02em',
          color: 'var(--fv-ink)', margin: '0 0 16px',
        }}>
          ¿Listo para ver cómo crecen tus dividendos?
        </h2>
        <p style={{ fontSize: 17, color: 'var(--fv-ink-70)', margin: '0 0 36px' }}>
          Importa tu cartera y ten tus métricas listas en menos de un minuto.
        </p>
        <div style={{ display: 'flex', gap: 16, justifyContent: 'center', alignItems: 'center' }}>
          <a href="/register" style={{
            background: 'var(--fv-ochre)', color: 'var(--fv-paper)',
            borderRadius: 'var(--fv-r-pill)', padding: '14px 28px',
            fontSize: 15, fontWeight: 500, textDecoration: 'none', display: 'inline-block',
          }}>
            Crear cuenta gratis →
          </a>
          <a href="/features" style={{ fontSize: 15, color: 'var(--fv-ink-70)', textDecoration: 'none' }}>
            Ver funcionalidades
          </a>
        </div>
      </section>

      <PublicFooter />
    </div>
  );
}
