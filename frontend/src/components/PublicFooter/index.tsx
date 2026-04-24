export function PublicFooter() {
  const linkStyle = { color: 'var(--fv-ink-40)', textDecoration: 'none' };
  return (
    <footer style={{ borderTop: '1px solid var(--fv-ink-10)', padding: '32px', textAlign: 'center' }}>
      <p style={{ fontSize: 13, color: 'var(--fv-ink-40)', margin: 0 }}>
        © 2025 FinView
        {' · '}<a href="/features" style={linkStyle}>Funcionalidades</a>
        {' · '}<a href="/pricing" style={linkStyle}>Precios</a>
        {' · '}<a href="/blog" style={linkStyle}>Blog</a>
      </p>
    </footer>
  );
}
