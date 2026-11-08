"use client";

import dynamic from "next/dynamic";
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

export default function LivingWorldClient() {
  return <WorldShell />;
}
