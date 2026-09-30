import { PublicNav } from '@/components/PublicNav';
import { PublicFooter } from '@/components/PublicFooter';

import blog from '@/app/blog/blog-post.module.css';
import styles from './legal.module.css';

/**
 * Shell for the legal documents. Reuses the blog's prose styles so the four
 * documents read like the rest of the public site without a second type scale.
 */
export default function LegalLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className={blog.page}>
      <PublicNav />
      <main className={blog.main}>
        <article className={`${blog.article} ${styles.legal}`}>
          {children}
        </article>
      </main>
      <PublicFooter />
    </div>
  );
}
