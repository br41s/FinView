import { PublicNav } from '@/components/PublicNav';
import { PublicFooter } from '@/components/PublicFooter';

import styles from '@/app/blog/blog-post.module.css';

/**
 * Shared shell for blog articles.
 *
 * Every post used to carry its own copy of this component plus its own
 * near-identical CSS module — 58 layouts and 58 stylesheets that differed
 * only by filename. Changing blog typography meant editing 58 files, or
 * realistically editing one and leaving 57 behind. The shell and its styles
 * now live here; each post's layout.tsx re-exports this.
 *
 * Four posts (declarar-dividendos-espana-guia-completa, dgi,
 * riesgo-divisa-cartera-dividendos, tramo-30-base-ahorro-irpf) genuinely
 * diverge — different table selectors and type scales — and deliberately
 * keep their own layout and stylesheet.
 */
export default function PostLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className={styles.page}>
      <PublicNav />
      <main className={styles.main}>
        <article className={styles.article}>{children}</article>
      </main>
      <PublicFooter />
    </div>
  );
}
