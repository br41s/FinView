# Holdings de fin de año para TR, DEGIRO e IBKR — memo de decisión (2026-09-25)

**Estado:** pendiente de decisión. **No implementado.** Ítem 5 de los diferidos de Fase 5.

## Hoy

- `_run_annual_import` guarda `PortfolioHolding` sólo para ING y BBVA (`_store_holdings`).
  TR (PDF), DEGIRO e IBKR parsean `report.holdings` y sólo lo **cuentan** en
  `counts["holdings"]`. eToro no parsea holdings; el CSV de TR tampoco.
- Sin filas no hay snapshot, así que `portfolio_service` usa sólo el ledger de esas tres
  cuentas. Da coste conocido, pero una cantidad que puede estar mal si falta historia.

## Qué hace un snapshot (lo que cambiaría)

- `_load_snapshots`: el año autoritativo de una cuenta es el mayor entre los imports con
  `portfolio_snapshot_complete=true` **y cualquier año que tenga filas**, sea cual sea
  el marcador.
- `_reconcile`:
  - **ISIN listado con cantidad distinta** (±0,01): toma la cantidad del snapshot y el
    coste pasa a desconocido (fail-closed).
  - **ISIN del ledger que el snapshot omite:** se cierra (cantidad 0 más las
    transacciones posteriores).
- **Verificado en memoria:** con filas y `portfolio_snapshot_complete=false`, una
  posición omitida se cierra igual que con `true` o `NULL`. El marcador sólo protege
  snapshots **vacíos**. Hoy no muerde porque los documentos parciales de ING y BBVA no
  traen filas, pero es una propiedad de esos importadores, no del loader.
- **Totales fail-closed:** una sola posición con coste desconocido deja la Cartera sin
  total invertido ni P&L.

## Medición: holdings reales de 2025 contra el ledger a 31/12

Ficheros de `files/` contra la BD local (usuario 1). La BD local puede ir por detrás de Neon.

| Broker | Filas | Coinciden | Cantidad distinta → coste desconocido | Sólo en el snapshot | En el ledger y omitidas → se cerrarían |
|---|---|---|---|---|---|
| DEGIRO (`DG-Informe Anual 2025.pdf`) | 8 | 8 | 0 | 0 | 0 |
| IBKR (`IBKR-U11040354_2025_2025.csv`) | 9 | 7 | 2 (ES0105684007 600→1300; US45841N1072 0,0169→6,99) | 0 | 0 |
| TR (`Tax report - Period ES IBAN-2025.pdf`) | 58 (1 sin ISIN) | 22 | 25 (p. ej. ES0139140174 550→850) | 10 | 3 (DE0007100000 80, US6092071058 30, NL0000379121 20) |

## Por broker

- **DEGIRO:** el certificado de fin de año coincide entero con el ledger. Persistir no
  cambia nada hoy. Sólo protege si el ledger se desviara más adelante. Riesgo y valor bajos.
- **IBKR:**
  - Corregiría 2 cantidades, que pasarían a coste desconocido.
  - `_extract_open_positions` sólo lee `Stocks`, así que bonos, fondos, opciones y forex
    no aparecen. Una fila omitida **cierra** la posición del ledger, y marcarlo `false`
    no lo impide (ver arriba).
  - El ISIN sale de un mapa de símbolos: si falta, la fila se descarta y la posición
    también se cerraría.
- **TR:**
  - Discrepa en 25 de 47 ISIN comunes. Eso apunta a un **ledger CSV incompleto**
    (probable historia DE anterior a la migración), no a un PDF equivocado.
  - Persistir corregiría las cantidades, pero dejaría la Cartera sin total invertido y
    cerraría 3 posiciones que el ledger mantiene.
  - En el año de migración hay dos PDF con `source_variant`. Si ambos guardan filas, el
    dict `latest` de `_load_snapshots` se queda con la última por (cuenta, ISIN), y la
    del periodo DE no es de fin de año.
  - El PDF no trae `price`: se guardaría 0. El fallback de `charts.py` usa
    `value_eur / quantity`, así que no le afecta.

## Riesgos

1. **Cierre silencioso** de posiciones que el documento no lista (IBKR no-Stocks, TR
   omitidas).
2. **Coste desconocido en cascada** hasta el total de la Cartera, por los totales
   fail-closed.
3. **Año de migración de TR:** dos snapshots parciales el mismo año.
4. **Cambia `portfolio_snapshot_complete` en la práctica:** hoy "filas ⇒ completo" se
   cumple porque ningún documento parcial trae filas. Con IBKR dejaría de cumplirse.
5. **Borrado y reemplazo ya cubiertos:** `_IMPORT_DEPENDENT_TABLES` incluye
   `PortfolioHolding` y los tres borrados en cascada lo limpian por `import_id`.

## Prerrequisito si se decide que sí

`_load_snapshots` debe tratar una importación con `portfolio_snapshot_complete=false`
como **parcial**. Sus filas reconcilian los ISIN que listan, pero no fijan el año
autoritativo que cierra a los omitidos. Cada importador declara el marcador: DEGIRO
`true` si está la sección del certificado, IBKR `false` por ser sólo `Stocks`, y TR
queda por decidir. Esto es un fix aislado y latente hoy; conviene hacerlo antes, con o
sin esta decisión.

## Tests que lo fijarían

1. `test_partial_snapshot_never_closes_an_omitted_position` (portfolio_service): una
   cuenta con BUY X y BUY Y, y un import `complete=false` con fila sólo para Y. X sigue
   abierta con su coste. **Hoy falla** (verificado).
2. Por broker, en `test_import_service`: importar con holdings crea filas
   `PortfolioHolding` con su `import_id` y el marcador esperado. Reimportar el año las
   sustituye y borrar el import las elimina.
3. Con ficheros reales, gated en `files/` mediante un fixture: el IBKR de 2025 no cierra
   ninguna posición del ledger ni cambia la cantidad de las 7 que coinciden.

## Recomendación

La decisión es de producto: **cantidad correcta frente a coste conocido**.

1. Hacer primero el prerrequisito del loader, como PR propio con el test 1.
2. **DEGIRO:** persistir con `complete=true`. No cambia nada hoy; es un seguro.
3. **IBKR:** persistir con `complete=false`, sólo después del punto 1.
4. **TR:** no persistir todavía. Antes, completar el ledger (historia DE) hasta que la
   tabla de arriba cuadre. Persistir hoy cambia 25 costes a "—" y cierra 3 posiciones.
