# Guía de usuario — FinView

FinView es un dashboard fiscal personal para inversores españoles. Agrega datos de múltiples brokers, calcula el FIFO cruzado y genera las casillas del Modelo 100 y Modelo 714 (IRPF).

---

## 1. Acceso

Abre [https://fin-view-topaz.vercel.app](https://fin-view-topaz.vercel.app) en el navegador.  
Si no tienes cuenta, pulsa **Regístrate** y crea una con tu email y contraseña. Para crearla
debes aceptar las [Condiciones de uso](https://fin-view-topaz.vercel.app/legal/condiciones) y la
[Política de privacidad](https://fin-view-topaz.vercel.app/legal/privacidad).

### Tus datos

En **Facturación › Cuenta** puedes:

- **Descargar mis datos**: un archivo JSON con todo lo que FinView guarda sobre ti.
- **Eliminar cuenta**: borra la cuenta y todos sus datos de forma inmediata e irreversible.
  Pide tu contraseña.

FinView es un producto de Biglobster LLC y hoy es gratuito. Es una herramienta informativa: no presta asesoramiento de inversión ni fiscal. Las
señales de Opciones, Zonas Clave e Ideas se generan automáticamente, en parte con IA.

---

## 2. Navegación rápida

Todas las páginas tienen un grupo de **6 iconos de acceso rápido** en la esquina superior derecha de la cabecera:

| Icono | Destino |
|-------|---------|
| Gráfico de barras | Dashboard fiscal |
| Maletín | Cartera |
| Actividad | Derivados (Options Monitor) |
| Diana | Técnico (Zonas Clave) |
| Globo | Ideas |
| Banco | Inversiones Alternativas |

El icono de la página actual aparece en color sólido para indicar dónde estás.

### Tema claro y oscuro

El botón de sol/luna en la cabecera cambia entre modo claro y oscuro. Por defecto FinView
sigue la preferencia de tu sistema operativo; en cuanto pulsas el botón, tu elección manda
y se recuerda en ese navegador.

---

## 3. Importar archivos de broker

### 3.1 Cómo importar

1. En el Dashboard, pulsa **Importar** (parte superior izquierda).
2. Arrastra el archivo sobre la zona marcada, o pulsa **Seleccionar archivos**.
3. También puedes usar los botones por broker (TR, DEGIRO, IBKR, ING, BBVA, eToro) para seleccionar directamente.
4. FinView procesa el archivo y muestra un resumen: dividendos, transacciones y ganancias importadas.

> **Duplicados:** Si subes el mismo archivo dos veces, FinView lo rechaza automáticamente.  
> **Reemplazo:** Si subes un archivo nuevo del mismo broker y año, reemplaza la importación anterior automáticamente.

> **Límite mensual:** tu plan incluye un número de importaciones al mes (5 en el plan Free).
> Puedes ver cuántas llevas en **Facturación**, junto al límite. Volver a subir un archivo
> que ya habías importado **no consume** ninguna: al estar deduplicado, nunca llegó a contar.
> El contador se reinicia el día 1 de cada mes.

### 3.2 Formatos por broker

| Broker | Formato | Cómo descargarlo |
|--------|---------|-----------------|
| **Trade Republic** | PDF o CSV | App TR → Cuenta → Documentos → Informe fiscal anual (PDF) o Exportar transacciones (CSV) |
| **DEGIRO** | PDF | Plataforma DEGIRO → Informes → Informes anuales → Informe Anual |
| **Interactive Brokers** | CSV | IBKR → Informes → Extractos de actividad → Anual → Formato CSV (incluir todas las secciones) |
| **ING** | PDF | ING Direct → Documentos → Información fiscal (soporta Certificado de Operaciones e Información Fiscal) |
| **BBVA** | 1-3 PDFs | BBVA Bróker → Documentos fiscales → Seleccionar los PDFs de operaciones, dividendos y patrimonio |
| **eToro** | XLSX | eToro → Configuración → Extractos de cuenta → Anual |

> Para BBVA, selecciona hasta 3 PDFs a la vez en el mismo diálogo de importación.

### 3.3 Acciones corporativas — resolución automática

Al importar, el agente supervisor detecta y resuelve automáticamente las inconsistencias más comunes:

| Tipo | Cómo se resuelve |
|------|-----------------|
| **Derechos (rights)** | Las ventas de derechos de suscripción se reclasifican automáticamente como dividendo. |
| **Scrip dividend** | Las acciones gratuitas con precio €0 se reconocen y marcan como válidas. |
| **Split con cambio de ISIN** | Si el mismo ticker tiene dos ISINs (antes y después del split), se detecta y confirma automáticamente sin acción del usuario. |
| **Split de cantidad** | Si el ratio del split coincide con la discrepancia en holdings (±5%), las cantidades se ajustan automáticamente (qty × ratio, precio / ratio). |
| **Ticker desconocido** | Se intenta resolver el ticker en Yahoo Finance automáticamente, y **se recuerda**: a partir de ahí el precio aparece y no se vuelve a buscar. Si no se encuentra, el aviso te deja escribirlo a mano (p. ej. `SAN.MC`) y esa corrección tiene prioridad sobre cualquier búsqueda posterior. |

Cuando no es posible resolver automáticamente, aparece un aviso de color **amarillo o rojo** tras la importación con el problema y los datos disponibles para que puedas revisarlo.

### 3.4 Eliminar importaciones

En la pantalla de importación, cada archivo tiene un icono de papelera. Al eliminar, se borran en cascada todas las transacciones, lotes FIFO, casillas y holdings asociados.  
El botón **Borrar todo** elimina todas las importaciones de todos los brokers a la vez.

---

## 4. Dashboard fiscal

Usa el selector **Año fiscal** (parte superior) para filtrar por año. Los datos se muestran en varias pestañas:

### Dashboard (resumen)
- Dividendos brutos y netos del año seleccionado
- Ganancias y pérdidas patrimoniales realizadas
- Retenciones en origen por país
- Distribución geográfica de dividendos (donut)
- Dividendos mensuales (gráfico de barras)
- Top pagadores del año

### Rendimiento
- Tabla de rendimiento de dividendos por empresa: rentabilidad sobre coste, sobre valor de mercado, dividendos totales recibidos, posición actual
- Empresas con split de ISIN se consolidan en una sola fila (los dividendos cobrados antes y después del split suman en la misma entrada)

### Dividendos
- Tabla completa de dividendos agregados por empresa (ISIN)
- Columnas: nombre, país, bruto, retención, neto, número de pagos
- Ordenable por cualquier columna

### Cartera
- Holdings a fin de año importados de cada broker
- Valor de mercado, precio medio, rentabilidad latente

### Comparativa anual
- Evolución de dividendos año a año (todos los años importados)
- Gráfico acumulado vs. por año

---

## 5. Casillas IRPF (Modelo 100 y 714)

En la pestaña **Rendimiento**, sección Casillas, encontrarás los valores precalculados para la declaración de la renta:

| Casilla | Descripción |
|---------|-------------|
| 27 | Intereses de cuentas y depósitos |
| 29 | Rendimientos del capital mobiliario (dividendos brutos) |
| 328 / 380 | Ganancias o pérdidas por categoría de activo (formato 2025) |
| 332 / 337 | Ganancias y pérdidas patrimoniales (formatos anteriores) |
| 588 | Deducción por doble imposición internacional |
| 597 | Retenciones españolas sobre capital mobiliario |
| 05-09 | Bienes en el extranjero — Modelo 714 |

> Los valores del FIFO cruzado pueden diferir de los calculados por cada broker individualmente. El importe de la casilla ya **incluye el ajuste FIFO**; la línea de ajuste explica cuánto se ha movido respecto al total informado por los brokers y evita sumarlo dos veces.

En **Mi declaración**, “Retenido en efectivo” explica lo descontado por los brokers.
Solo el pago a cuenta español y la deducción exterior aplicable reducen el resultado.
Si una importación antigua no contiene el desglose origen/destino, FinView muestra un
aviso y no lo estima: vuelve a importar el informe fiscal de ese ejercicio.

---

## 6. Cartera (portfolio)

La página **Cartera** muestra tus posiciones abiertas con precios en tiempo real de Yahoo Finance.

### Resumen
- Valor de mercado total, capital invertido, rentabilidad latente

El valor de mercado puede seguir mostrándose aunque FinView no conozca el coste de
alguna posición. En ese caso, **capital invertido** y **rentabilidad latente** aparecen
como “— / Coste incompleto”: no se sustituye el coste ausente por cero. Esto puede
ocurrir con un spin-off o cuando el historial anterior al último snapshot está incompleto.
Si Yahoo no devuelve el precio de algún activo, el total muestra “Valoración incompleta”
en vez de sumar solo las posiciones que sí tienen precio.

Las operaciones posteriores al último informe anual siempre se aplican sobre ese
snapshot. Si un informe de patrimonio confirma que la cartera quedó vacía, las
posiciones de años anteriores desaparecen y una compra posterior las reabre normalmente.

### Tabla de posiciones
Al desplegar una posición verás un resumen con: ISIN, **Valor actual** (precio de mercado × cantidad), rentabilidad latente (%), peso en cartera y país. Además:
- **Desglose por cuenta:** cantidad y coste por broker
- **Dividendos cobrados:** tabla anual (año, importe bruto, neto, número de pagos). Los pagos del mismo año se consolidan en una sola fila aunque el broker los haya registrado con fecha fiscal.
- **Historial de operaciones:** compras y ventas, excluyendo dividendos (que aparecen en la sección anterior)

### Añadir a Zonas Clave
El icono de diana junto a cada posición la añade a la watchlist de Zonas Clave. Aparece un mensaje verde de confirmación con un botón **"Ir a Zonas Clave"** para navegar directamente.

---

## 7. Monitor de opciones (Derivados)

La página **Derivados** permite monitorizar posiciones en opciones financieras.

### 7.1 Pestañas

| Pestaña | Contenido |
|---------|-----------|
| **Watchlist** | La lista única: tus posiciones de cartera se añaden solas, más los tickers que añadas a mano. Una fila por ticker con Sentimiento, P/C ratio y badge IV vs HV. Al pulsar una fila se despliega su gráfico y su cadena de opciones |
| **Monitor** | Todo lo que ha disparado, en tres vistas: **Alertas** (del agente de opciones), **Smart Money** (actividad inusual) y **Técnico** (precios acercándose a una zona clave). Cada alerta lleva atajos a la sección relevante |
| **Backtesting** | Precisión de señales pasadas a +1d, +3d y +7d, por tipo de señal y por régimen macro |
| **IA** | Último informe del agente en 7 secciones, con metadatos del ciclo, y chat |
| **Agente** | Estado del scheduler y métricas de ciclo |

> **Cartera y Watchlist eran dos pestañas** hasta que se fusionaron: tus posiciones ya se
> añadían solas a la watchlist, así que enseñaban los mismos tickers dos veces.

> **Borrar es asimétrico a propósito.** Los tickers que tienes en cartera solo ofrecen
> "Ocultar" — un borrado normal lo desharía la sincronización automática al recargar. Los
> que añadiste a mano sí tienen "Eliminar".

### 7.2 Watchlist

Añade los tickers que quieres vigilar (por ejemplo: `AAPL`, `IBE.MC`, `MSFT`).  
Los tickers con sufijo `.MC` se consultan en MEFF (mercado español de derivados); los sufijos europeos (`.DE`, `.PA`, `.AS`, etc.) en Eurex; el resto en Yahoo Finance.

- **Activar/desactivar:** Cada ticker se puede pausar individualmente sin eliminarlo.
- **Eliminar:** Al eliminar un ticker de la watchlist se borran también sus snapshots, alertas y actividad inusual asociados.
- **Barra de sentimiento global:** muestra el P/C ratio agregado de todos los tickers activos con etiqueta Alcista / Neutral / Bajista.

### 7.3 Ciclos de análisis

El agente ejecuta ciclos periódicos (cada 30 minutos en horario de mercado, de lunes a viernes entre las 7:00 y las 22:59 UTC) para cada ticker activo de tu watchlist:

1. **Observar:** Descarga la cadena de opciones (calls y puts) del mercado.
2. **Greeks:** Calcula delta, gamma, theta, vega y rho con Black-Scholes.
3. **Analizar:** Detecta alertas de IV alta, ratios Put/Call extremos, skew y actividad inusual.
4. **Premium Spike:** Detecta saltos bruscos de prima. Se activa cuando la prima actual ≥ 2,5× la media móvil exponencial y la muestra tiene ≥ 3 ciclos acumulados.
5. **Almacenar:** Guarda snapshot, alertas y actividad inusual en la base de datos.
6. **Notificar:** Si hay alertas de severidad HIGH, envía notificaciones push (ntfy), email y Telegram.
7. **Análisis Claude:** Si hay alertas, ejecuta un análisis narrativo con IA estructurado en 7 secciones (visible en la pestaña Análisis).

Puedes lanzar un ciclo manualmente con el botón **Ejecutar ciclo**.

### 7.4 Alertas

Las alertas se generan automáticamente cuando:

| Tipo | Condición |
|------|-----------|
| HIGH_IV | IV media > 50% |
| HIGH_PUT_CALL_RATIO | P/C ratio > 1.5 (sentimiento bajista) |
| LOW_PUT_CALL_RATIO | P/C ratio < 0.5 (sentimiento alcista) |
| IV_SKEW | Diferencia IV puts vs calls > 10 pp |
| IV_PREMIUM | IV media > 1.5× la volatilidad histórica |

Puedes marcar alertas como leídas individualmente o todas a la vez.

### 7.5 HV vs IV badge

En la pestaña **Cartera**, cada ticker muestra un badge de comparación entre la volatilidad implícita (IV) y la volatilidad histórica (HV):

- **IV cara** — IV > HV + 5 pp (opciones caras, prima elevada)
- **IV normal** — dentro del rango
- **IV barata** — IV < HV − 5 pp (opciones baratas, posible oportunidad)

Para tickers `.MC`, la HV se calcula a partir de 60 días de histórico de Yahoo Finance.

### 7.6 Pestaña Análisis

Muestra el último análisis generado por Claude durante un ciclo del agente. Incluye:

- **Cabecera del ciclo:** timestamp, tickers analizados, total de alertas y sentimiento global.
- **7 secciones:** Resumen Ejecutivo · Smart Money · Señales Greeks · Top Picks · Catalizadores · Contexto MEFF (solo si hay tickers `.MC`) · Gestión de Riesgo.

### 7.7 Snapshots y cadena de opciones

Cada ciclo guarda un snapshot por ticker con volumen y Open Interest de calls/puts, ratio Put/Call, IV media, volatilidad histórica (HV), IV Skew y sentimiento (BULLISH / NEUTRAL / BEARISH).

---

## 8. Zonas Clave (Técnico)

La página **Zonas Clave** calcula soportes, resistencias y tendencia algorítmica para los tickers de tu watchlist.

### 8.1 Watchlist

Añade tickers manualmente (campo de texto) o directamente desde la **Cartera** usando el icono de diana junto a cada posición.

### 8.2 Análisis por ticker

Para cada ticker se calcula:

| Campo | Descripción |
|-------|-------------|
| **Zonas de soporte/resistencia** | Niveles de precio con número de toques y score de volumen (0–1) |
| **RSI** | Índice de fuerza relativa (14 períodos) |
| **MACD** | Señal: bullish / bearish / neutral |
| **Tendencia** | % sesgo alcista y bajista sobre el histórico |
| **Precio actual** | Último precio conocido |
| **Gráfico** | Precio histórico + zonas marcadas visualmente |

### 8.3 Actualización

- **Manual:** Botón "Actualizar todo" recalcula todos los tickers de la watchlist.
- **Automático (24h):** El scheduler recalcula cada 24 horas cuando está activo.

---

## 9. Ideas

La página **Ideas** es la mesa de tesis: dónde se plantea *por qué* algo podría ser una
oportunidad. La siembran eventos geopolíticos y naturales (terremotos, conflictos,
incendios, rutas marítimas, meteorología), que se cruzan con reglas para producir señales
de mercado.

Un mapa muestra dónde está pasando cada cosa; la lista lateral, las señales activas.

### 9.1 Qué te dice una señal

Al seleccionar una señal, el panel te da:

| Bloque | Qué es |
|--------|--------|
| **Importancia / Confianza / Riesgo / Dirección** | Cómo de fuerte es la señal y hacia dónde apunta |
| **Why this was triggered** | Las reglas que casaron, cada una con su tesis (por qué mueve mercados) y su confianza |
| **Tickers afectados** | Con dirección propia por ticker — una misma señal puede ser alcista para uno y bajista para otro |
| **Checkpoints** | El seguimiento del acierto a 1h, 6h, 1d, 3d y 7d. Se van rellenando con el tiempo |

### 9.2 Qué puedes hacer

Al pulsar un ticker se despliega su **gráfico de precio** y sus **fundamentales**
(capitalización, PER, márgenes, deuda, ROE…), más:

- **Añadir a Zonas Clave** — lo manda a la mesa técnica y lanza su análisis de
  soportes/resistencias. Un clic.
- Enlaces a **Zonas Clave** y **Derivados** ya centrados en ese ticker.

> Los fundamentales son **contexto para que tú decidas**. No alimentan ninguna señal ni
> puntuación: nada de lo que ves ahí cambia lo que el sistema te alerta.

### 9.3 Por qué aquí no hay opciones

Cada página tiene un trabajo: **Zonas Clave** dice *cuándo* mirar (el técnico), **Ideas**
dice *por qué* (la tesis) y **Derivados** dice *cómo* ejecutarlo con PUT/CALL. Por eso no
verás cadenas de opciones en Ideas ni tesis de inversión en Derivados — solo enlaces entre
ellas.

---

## 10. Inversiones Alternativas

La página **Inversiones Alternativas** (icono del banco) te permite hacer seguimiento manual de tus inversiones de banca privada que no encajan en los brokers tradicionales: private equity, venture capital, real estate, hedge funds, productos estructurados y otros.

> Es una herramienta de seguimiento manual: no importa archivos ni usa IA. Tú introduces las cifras y FinView calcula las métricas.

### 9.1 Añadir una inversión

Pulsa **Añadir** y rellena el formulario:

| Campo | Descripción |
|-------|-------------|
| **Nombre** | Nombre del fondo o producto (obligatorio) |
| **Tipo** | Private Equity, Venture Capital, Real Estate, Hedge Fund, Producto Estructurado u Otro |
| **Estado** | Activa o Realizada |
| **Gestora / Banco** | Quién gestiona la inversión |
| **Año (vintage)** | Año de constitución/entrada |
| **Geografía / Divisa** | Exposición geográfica y moneda |
| **Capital comprometido** | Total comprometido al fondo |
| **Capital desembolsado (called)** | Lo que ya has aportado |
| **Distribuido** | Lo que el fondo te ha devuelto |
| **NAV actual** | Valor liquidativo actual de tu posición |

Puedes editar o eliminar cualquier posición con los iconos de la tabla.

### 9.2 Métricas calculadas

A partir de las cifras que introduces, FinView calcula automáticamente las métricas estándar del private equity:

| Métrica | Significado |
|---------|-------------|
| **TVPI** | Valor total / capital desembolsado = (distribuido + NAV) / called |
| **DPI** | Distribuido / desembolsado — cuánto te han devuelto ya |
| **RVPI** | NAV / desembolsado — cuánto valor queda por realizar |
| **Sin desembolsar (unfunded)** | Comprometido − desembolsado |
| **Valor total** | Distribuido + NAV |

### 9.3 Consolidación

Las tarjetas superiores resumen el total de la cartera (comprometido, desembolsado, NAV, TVPI/DPI) y las barras de **asignación por tipo** muestran qué porcentaje de tu NAV está en cada categoría.

### 9.4 Buscar en el catálogo CNMV

En la parte superior de la página hay un **buscador**. Escribe el nombre de un fondo (o su ISIN) y aparecerá un desplegable con los fondos registrados en la **CNMV** que coinciden. Cada resultado muestra su **NAV por participación** y su **patrimonio** (tamaño del fondo). Al seleccionar uno, el formulario de alta se rellena automáticamente con su **nombre, tipo, gestora e ISIN** — solo tienes que añadir los importes (comprometido, desembolsado, distribuido, NAV), que son personales y no figuran en el registro público.

- **Ordenar y filtrar:** junto al buscador puedes ordenar por *mayor patrimonio*, *mayor/menor NAV*, y fijar un *patrimonio mínimo* (en millones de €). Con esos controles puedes **explorar** el catálogo (p. ej. ver los fondos más grandes) sin escribir ningún nombre.
- Cubre los **fondos de inversión españoles** registrados en la CNMV (~1.400 fondos), todos con NAV y patrimonio. SICAV, IIC inmobiliarias, hedge funds y capital riesgo (private equity / venture capital) aún no están en el buscador — añádelos manualmente con "Añadir".
- Las métricas de private equity (DPI, TVPI, IRR, vintage, comprometido, hurdle…) no figuran en ninguna fuente pública gratuita: se introducen a mano en la ficha de cada inversión.
- Si no encuentras tu inversión (por ejemplo, un producto de banca privada a medida o un fondo extranjero), usa "Añadir" para introducirla a mano.

---

## 11. Preguntas frecuentes

**¿Por qué las ganancias calculadas difieren de las del broker?**  
Cada broker calcula su FIFO internamente. FinView recalcula el FIFO combinando todos los brokers en una única cronología: las ventas de años anteriores consumen primero las compras antiguas y nunca se usa una compra posterior a la venta. La diferencia se reparte entre las casillas 332 y 337 y ya está incluida en los totales mostrados.

Si falta inventario para cubrir una venta o el ISIN está vacío, FinView no publica un
resultado FIFO parcial como definitivo. Revisa la calidad de las importaciones antes de
usar esas cifras.

Si la cronología alcanza acciones recibidas por **spin-off** cuyo coste de adquisición
no figura en los documentos, aparece el aviso `missing_cost_basis`. La cantidad sí se
consume en orden FIFO, pero FinView no inventa un coste cero ni publica el ajuste del
ejercicio hasta que ese dato sea conocido; ese bloqueo anual aparece como
`fifo_missing_cost_basis`. En el aviso fuente puedes introducir el **coste por acción**;
debe ser un número mayor que cero. FinView actualiza solo el lote indicado y recalcula
automáticamente el ejercicio y los posteriores. Si recibiste varias entregas del mismo
ISIN, cada una conserva su propio aviso hasta completar su coste.

**¿Por qué ha desaparecido un ajuste FIFO antiguo?**

Los resultados calculados antes de FIFO v2 no contienen el desglose fiable entre
ganancias y pérdidas y se ignoran de forma segura. Reemplaza o reimporta el ejercicio
para regenerar sus lotes y ajustes con el motor actual. No se hace un backfill automático.

**¿Por qué aparece Aena (u otra empresa) dos veces en Rendimiento?**  
Cuando una empresa cambia de ISIN (por ejemplo, en un split accionarial), el broker puede reportar dividendos bajo ambos ISINs. FinView los detecta automáticamente y los consolida en una sola fila usando el ticker de Yahoo Finance como referencia.

**¿Puedo importar varios años?**  
Sí. Cada importación se asocia a un año fiscal. Puedes tener datos de múltiples años de múltiples brokers simultáneamente.

**¿Puedo importar el mismo broker varias veces en el mismo año?**  
No — si ya existe una importación para ese broker + año, la nueva reemplaza a la anterior automáticamente.

**¿Qué pasa con las asignaciones de opciones de IBKR?**  
Las asignaciones se detectan automáticamente por los trade codes del extracto IBKR. Se
registran en tabla separada y son visibles en la pestaña de ganancias. La prima se aplica
una sola vez a la operación de acciones: reduce el coste en una PUT asignada y aumenta el
importe de venta en una CALL asignada. Si ya habías importado un extracto IBKR anterior a
esta corrección, reemplázalo para regenerar los importes.

**¿Tengo que volver a importar informes DEGIRO antiguos?**

Sí, si quieres que las comisiones e impuestos de transacción corrijan lotes ya
persistidos. Reemplazar el informe recalcula también cualquier venta posterior que
dependa de esas compras históricas.

**¿Qué tickers puedo añadir al monitor de opciones?**  
Cualquier ticker con opciones en Yahoo Finance (acciones US/EU) o en MEFF (tickers con sufijo `.MC` como `IBE.MC`, `SAN.MC`).

**¿Qué tickers puedo añadir a Zonas Clave?**  
Cualquier ticker que Yahoo Finance reconozca. Para bolsa española usa el sufijo `.MC` (ej. `SAN.MC`, `ITX.MC`).
