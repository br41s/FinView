# Guía de usuario — FinView

FinView es un dashboard fiscal personal para inversores españoles. Agrega datos de múltiples brokers, calcula el FIFO cruzado y genera las casillas del Modelo 100 y Modelo 714 (IRPF).

---

## 1. Acceso

Abre [https://fin-view-topaz.vercel.app](https://fin-view-topaz.vercel.app) en el navegador.  
Si no tienes cuenta, pulsa **Regístrate** y crea una con tu email y contraseña.

---

## 2. Importar archivos de broker

### 2.1 Cómo importar

1. En el Dashboard, pulsa **Importar** (parte superior izquierda).
2. Arrastra el archivo sobre la zona marcada, o pulsa **Seleccionar archivos**.
3. También puedes usar los botones por broker (TR, DEGIRO, IBKR, ING, BBVA, eToro) para seleccionar directamente.
4. FinView procesa el archivo y muestra un resumen: dividendos, transacciones y ganancias importadas.

> **Duplicados:** Si subes el mismo archivo dos veces, FinView lo rechaza automáticamente.  
> **Reemplazo:** Si subes un archivo nuevo del mismo broker y año, reemplaza la importación anterior automáticamente.

### 2.2 Formatos por broker

| Broker | Formato | Cómo descargarlo |
|--------|---------|-----------------|
| **Trade Republic** | PDF o CSV | App TR → Cuenta → Documentos → Informe fiscal anual (PDF) o Exportar transacciones (CSV) |
| **DEGIRO** | PDF | Plataforma DEGIRO → Informes → Informes anuales → Informe Anual |
| **Interactive Brokers** | CSV | IBKR → Informes → Extractos de actividad → Anual → Formato CSV (incluir todas las secciones) |
| **ING** | PDF | ING Direct → Documentos → Información fiscal |
| **BBVA** | 1-3 PDFs | BBVA Bróker → Documentos fiscales → Seleccionar los PDFs de operaciones, dividendos y patrimonio |
| **eToro** | XLSX | eToro → Configuración → Extractos de cuenta → Anual |

> Para BBVA, selecciona hasta 3 PDFs a la vez en el mismo diálogo de importación.

### 2.3 Eliminar importaciones

En la pantalla de importación, cada archivo tiene un icono de papelera. Al eliminar, se borran en cascada todas las transacciones, lotes FIFO, casillas y holdings asociados.

---

## 3. Dashboard fiscal

Usa el selector **Año fiscal** (parte superior) para filtrar por año. Los datos se muestran en varias pestañas:

### Dashboard (resumen)
- Dividendos brutos y netos del año seleccionado
- Ganancias y pérdidas patrimoniales realizadas
- Retenciones en origen por país
- Distribución geográfica de dividendos (donut)
- Dividendos mensuales (gráfico de barras)
- Top pagadores del año

### Rendimiento
- Tarjetas: dividendos brutos, netos, ganancias, pérdidas, retenciones extranjeras
- Desglose de retenciones por país de origen del dividendo

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

## 4. Casillas IRPF (Modelo 100 y 714)

En la pestaña **Rendimiento**, sección Casillas, encontrarás los valores precalculados para la declaración de la renta:

| Casilla | Descripción |
|---------|-------------|
| 27 | Intereses de cuentas y depósitos |
| 29 | Rendimientos del capital mobiliario (dividendos brutos) |
| 332 | Ganancias patrimoniales a corto plazo (<1 año) |
| 337 | Pérdidas patrimoniales a corto plazo |
| 05-09 | Bienes en el extranjero — Modelo 714 |

> Los valores del FIFO cruzado pueden diferir de los calculados por cada broker individualmente. FinView muestra el **ajuste FIFO** cuando existe diferencia — es el valor que Hacienda exige declarar.

---

## 5. Monitor de opciones

La pestaña **Opciones** permite monitorizar posiciones en derivados financieros.

### 5.1 Watchlist

Añade los tickers que quieres vigilar (por ejemplo: `AAPL`, `IBE.MC`, `MSFT`).  
Los tickers con sufijo `.MC` se consultan en MEFF (bolsa española); el resto en Yahoo Finance.

- **Activar/desactivar:** Cada ticker se puede pausar individualmente sin eliminarlo.
- **Eliminar:** Botón de papelera junto al ticker.

### 5.2 Ciclos de análisis

El agente ejecuta ciclos periódicos (cada 15 minutos por defecto) para cada ticker de tu watchlist:

1. **Observar:** Descarga la cadena de opciones (calls y puts) del mercado.
2. **Greeks:** Calcula delta, gamma, theta, vega y rho con Black-Scholes.
3. **Analizar:** Detecta alertas de IV alta, ratios Put/Call extremos, skew y actividad inusual.
4. **Almacenar:** Guarda un snapshot con el estado del mercado.
5. **Notificar:** Si hay alertas de severidad HIGH, envía notificaciones push (ntfy) y email.
6. **Análisis Claude:** Si hay alertas, ejecuta un análisis narrativo con IA.

Puedes lanzar un ciclo manualmente con el botón **Ejecutar ciclo**.

### 5.3 Snapshots y cadena de opciones

Cada ciclo guarda un snapshot por ticker con:
- Volumen y Open Interest de calls/puts
- Ratio Put/Call (volumen y OI)
- IV media de calls y puts
- Volatilidad histórica (30 días)
- IV Skew (puts vs calls)
- Sentimiento de mercado: BULLISH / NEUTRAL / BEARISH

### 5.4 Alertas

Las alertas se generan automáticamente cuando:

| Tipo | Condición |
|------|-----------|
| HIGH_IV | IV media > 50% |
| HIGH_PUT_CALL_RATIO | P/C ratio > 1.5 (sentimiento bajista) |
| LOW_PUT_CALL_RATIO | P/C ratio < 0.5 (sentimiento alcista) |
| IV_SKEW | Diferencia IV puts vs calls > 10 pp |
| IV_PREMIUM | IV media > 1.5× la volatilidad histórica |

Puedes marcar alertas como leídas individualmente o todas a la vez.

### 5.5 Actividad inusual (Smart Money)

Se detecta cuando el volumen de una opción supera 3× su Open Interest. Puede indicar posicionamiento institucional.

---

## 6. Preguntas frecuentes

**¿Por qué las ganancias calculadas difieren de las del broker?**  
Cada broker calcula su FIFO internamente. FinView recalcula el FIFO combinando todos los brokers cronológicamente, como exige Hacienda. La diferencia se muestra como "ajuste FIFO".

**¿Puedo importar varios años?**  
Sí. Cada importación se asocia a un año fiscal. Puedes tener datos de múltiples años de múltiples brokers simultáneamente.

**¿Puedo importar el mismo broker varias veces en el mismo año?**  
No — si ya existe una importación para ese broker + año, la nueva reemplaza a la anterior automáticamente.

**¿Qué pasa con las asignaciones de opciones de IBKR?**  
Las asignaciones se detectan automáticamente por los trade codes del extracto IBKR. Se registran en tabla separada y son visibles en la pestaña de ganancias.

**¿Qué tickers puedo añadir al monitor de opciones?**  
Cualquier ticker con opciones en Yahoo Finance (acciones US/EU) o en MEFF (tickers con sufijo `.MC` como `IBE.MC`, `SAN.MC`).
