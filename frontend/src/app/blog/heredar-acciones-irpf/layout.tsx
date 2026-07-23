import { PublicNav } from '@/components/PublicNav';
import { PublicFooter } from '@/components/PublicFooter';
import styles from './heredar-acciones-irpf.module.css';

export default function HeredarAccionesLayout({ children }: { children: React.ReactNode }) {
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
