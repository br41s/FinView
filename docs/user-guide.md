# Guía de usuario — FinView

## 1. Acceso

Abrir `http://localhost:3000` en el navegador.

## 2. Importar archivos

1. Pulsar **"Importar archivo"** en la parte superior
2. Arrastrar o seleccionar el archivo del broker
3. FinView detecta automáticamente el broker por el contenido:
   - **Trade Republic:** PDF del Steuerbericht anual
   - **DEGIRO:** PDF del Informe Anual
   - **Interactive Brokers:** CSV del Activity Statement (exportar desde IBKR como CSV)
   - **ING:** PDF de Información Fiscal
   - **BBVA:** 1-3 PDFs (operaciones, dividendos, patrimonio) — seleccionar todos a la vez
   - **eToro:** XLSX del Account Statement anual
4. Se muestra un resumen con el número de transacciones, dividendos y holdings importados

> **Duplicados:** Si intentas importar el mismo archivo dos veces, FinView lo rechaza automáticamente.

## 3. Seleccionar año fiscal

Usar el selector de año en la parte superior del dashboard. Se muestran solo los años con datos importados.

## 4. Pestañas del dashboard

### Gráficas
- **Dividendos por país:** Distribución geográfica (donut)
- **Dividendos mensuales:** Ingresos por mes (barras)
- **Top pagadores:** Las 10 empresas que más dividendos pagaron
- **Ganancias/pérdidas:** Desglose por ISIN (barras horizontales)
- **Composición patrimonio:** Distribución de cartera a fin de año
- **Retenciones por país:** Impuestos retenidos por país de origen
- **Historial por empresa:** Evolución de dividendos por empresa

### Rendimiento
- Tarjetas resumen: dividendos brutos/netos, ganancias, pérdidas, retenciones extranjeras
- Desglose por país de las retenciones

### Casillas (Modelo 100 y 714)
- **Casilla 27:** Intereses
- **Casilla 29:** Rendimientos del capital mobiliario (dividendos)
- **Casilla 332:** Ganancias patrimoniales (holding >1 año)
- **Casilla 337:** Pérdidas patrimoniales
- **Casillas 05-09:** Patrimonio en el extranjero (Modelo 714)
- Se muestra el desglose por broker y los ajustes FIFO si los hay

### Dividendos
- Tabla con todos los dividendos agregados por ISIN
- Columnas: nombre, país, bruto, retención, neto, nº pagos
- Ordenable por cualquier columna

### Ganancias de capital
- Tabla con cada lote FIFO realizado
- Incluye: broker compra/venta, ISIN, cantidad, coste, venta, P&L, periodo
- Indicador de ajuste FIFO si el cruzado difiere del broker

## 5. Eliminar importaciones

En la sección de importaciones (`GET /imports/`), cada importación puede eliminarse. Esto borra en cascada todas las transacciones, lotes FIFO, casillas y holdings asociados.

## 6. Formatos de archivo por broker

### Trade Republic
- Descargar el **"Informe fiscal anual"** (Steuerbericht) desde la app TR
- Formato: PDF con secciones I a IX

### DEGIRO
- Descargar el **"Informe Anual"** desde DEGIRO → Informes → Informes anuales
- Formato: PDF con dividendos, ganancias, cartera y transacciones

### Interactive Brokers
- En IBKR → Informes → Extractos de actividad → Anual → Formato CSV
- Asegurarse de incluir todas las secciones (trades, dividends, positions)

### ING
- Descargar **"Información Fiscal"** desde ING Direct → Documentos → Información fiscal
- Formato: PDF

### BBVA
- Se necesitan hasta 3 PDFs separados:
  1. **Operaciones** (compras/ventas)
  2. **Dividendos** (rendimientos)
  3. **Patrimonio** (cartera a fin de año)
- Seleccionar los 3 en el diálogo de importación

### eToro
- Descargar **"Account Statement"** anual desde eToro → Configuración → Extractos
- Formato: XLSX con múltiples hojas (Account Summary, Dividends, Closed Positions, etc.)

## 7. Preguntas frecuentes

**¿Por qué las ganancias de un broker difieren del FIFO cruzado?**
Cada broker calcula su propio FIFO internamente. FinView recalcula el FIFO combinando las compras/ventas de TODOS los brokers cronológicamente, como exige Hacienda. La diferencia se muestra como "ajuste FIFO".

**¿Qué pasa con las opciones de IBKR?**
Las asignaciones de opciones se detectan automáticamente por los trade codes. Se registran en una tabla separada y son visibles en la pestaña de ganancias.

**¿Puedo importar varios años del mismo broker?**
Sí, cada importación se asocia a un año fiscal concreto. Solo se rechaza reimportar el mismo archivo exacto o el mismo broker+año.
