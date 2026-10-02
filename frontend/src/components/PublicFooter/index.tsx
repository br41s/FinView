import { NOT_ADVICE } from '@/lib/legal';
import styles from './index.module.css';

export function PublicFooter() {
  return (
    <footer className={styles.footer}>
      <p className={styles.text}>
        © {new Date().getFullYear()} FinView
        {' · '}<a href="/features" className={styles.link}>Funcionalidades</a>
        {' · '}<a href="/pricing" className={styles.link}>Precios</a>
        {' · '}<a href="/blog" className={styles.link}>Blog</a>
      </p>
      <p className={styles.text}>
        <a href="/legal/aviso-legal" className={styles.link}>Aviso legal</a>
        {' · '}<a href="/legal/privacidad" className={styles.link}>Privacidad</a>
        {' · '}<a href="/legal/cookies" className={styles.link}>Cookies</a>
        {' · '}<a href="/legal/condiciones" className={styles.link}>Condiciones</a>
      </p>
      <p className={styles.disclaimer}>
        {NOT_ADVICE.short} Tampoco es asesoramiento fiscal. El contenido del blog es divulgativo.
        Invertir conlleva riesgo de pérdida.
      </p>
    </footer>
  );
}
