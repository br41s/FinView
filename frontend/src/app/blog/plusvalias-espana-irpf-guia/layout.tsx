import { PublicNav } from '@/components/PublicNav';
import { PublicFooter } from '@/components/PublicFooter';
import styles from './plusvalias-espana-irpf-guia.module.css';

export default function PlusvaliasLayout({ children }: { children: React.ReactNode }) {
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
