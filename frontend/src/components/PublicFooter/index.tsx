import styles from './index.module.css';

export function PublicFooter() {
  return (
    <footer className={styles.footer}>
      <p className={styles.text}>
        © 2025 FinView
        {' · '}<a href="/features" className={styles.link}>Funcionalidades</a>
        {' · '}<a href="/pricing" className={styles.link}>Precios</a>
        {' · '}<a href="/blog" className={styles.link}>Blog</a>
      </p>
    </footer>
  );
}
