"use client";

import Link from "next/link";
import dynamic from "next/dynamic";
import { useWorldData } from "./hooks/useWorldData";
import s from "./world.module.css";

/**
 * Three.js is only imported here, behind `ssr: false`, so no other route pays for it and
 * the server never touches WebGL. The shell is usable (and the page says so) while the
 * 3D bundle downloads.
 */
const WorldShell = dynamic(() => import("./components/WorldShell"), {
  ssr: false,
  loading: () => (
    <div className={s.root}>
      <div className={s.center} role="status">
        <div className={s.card}>Cargando el pueblo…</div>
      </div>
    </div>
  ),
});

function Message({ title, children }: Readonly<{ title?: string; children: React.ReactNode }>) {
  return (
    <div className={s.root}>
      <div className={s.center}>
        <div className={s.card} role="status">
          {title && <h2 style={{ marginTop: 0 }}>{title}</h2>}
          {children}
        </div>
      </div>
    </div>
  );
}

const Actions = ({ children }: Readonly<{ children: React.ReactNode }>) => (
  <div className={s.actions} style={{ justifyContent: "center", marginTop: 12 }}>
    {children}
  </div>
);

/** `demo`: the fictional Phase 0 town, nothing fetched (`/living-world?demo=1`). */
export default function LivingWorldClient({ demo = false }: Readonly<{ demo?: boolean }>) {
  const data = useWorldData(demo);

  if (data.status === "loading") return <Message>Cargando tu cartera…</Message>;

  if (data.status === "error") {
    return (
      <Message title="No se puede cargar el pueblo">
        <p>{data.message}</p>
        <Actions>
          <button className={s.btn} onClick={data.retry}>
            Reintentar
          </button>
          <Link className={`${s.btn} ${s.linkBtn}`} href="/living-world?demo=1">
            Ver el pueblo de demostración
          </Link>
        </Actions>
      </Message>
    );
  }

  if (data.status === "empty") {
    return (
      <Message title="Tu pueblo está vacío">
        <p>Aún no tienes posiciones abiertas. Importa tus operaciones y cada empresa de tu cartera tendrá su edificio.</p>
        <Actions>
          <Link className={`${s.btn} ${s.linkBtn}`} href="/dashboard?view=importar">
            Importar operaciones
          </Link>
          <Link className={`${s.btn} ${s.linkBtn}`} href="/living-world?demo=1">
            Ver el pueblo de demostración
          </Link>
        </Actions>
      </Message>
    );
  }

  return (
    <WorldShell
      key={demo ? "demo" : "real"}
      assets={data.assets}
      realEvents={data.events}
      demo={demo}
      meta={data.meta}
      onRefresh={demo ? null : data.refresh}
      refreshing={data.refreshing}
      refreshFailed={data.refreshFailed}
    />
  );
}
