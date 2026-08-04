import { PublicNav } from '@/components/PublicNav';
import { PublicFooter } from '@/components/PublicFooter';
import styles from './bonos-renta-fija-fiscalidad-irpf.module.css';

export default function BonosRentaFijaLayout({ children }: { children: React.ReactNode }) {
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
