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

const POSTS: Post[] = [
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
