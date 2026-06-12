import { PublicNav } from '@/components/PublicNav';
import { PublicFooter } from '@/components/PublicFooter';
import styles from './modelo-720-bienes-extranjero.module.css';

export default function Modelo720Layout({ children }: { children: React.ReactNode }) {
  return (
    <div className={styles.page}>
      <PublicNav />
      <main className={styles.main}>
        <article className={styles.article}>
          {children}
        </article>
      </main>
      <PublicFooter />
    </div>
  );
}
