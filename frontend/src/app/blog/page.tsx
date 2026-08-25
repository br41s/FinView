import { PublicNav } from '@/components/PublicNav';
import { PublicFooter } from '@/components/PublicFooter';
import styles from './blog.module.css';
import { POST_IMAGES } from './postImages';
import { blogPosts } from './posts';

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
  const posts = blogPosts();

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
          {posts.map(({ slug, tag, date, readTime, title, excerpt }) => {
            const Image = POST_IMAGES[slug];
            return (
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
            );
          })}
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
