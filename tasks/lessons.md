# Lessons

Correcciones del usuario → reglas para no repetir el error.

## Agregados cruzados deben cuadrar

**Patrón:** Al tocar un cálculo que se muestra también en otro sitio
(ej. total anual de dividendos en el dashboard vs desglose por país),
verificar que ambas vistas usen la misma fuente de datos y el mismo
filtro antes de dar por terminado.

**Regla:** Si el dashboard y un desglose responden a la misma pregunta
("¿cuánto dividendo en 2025?"), el backend debe calcularlos con la
misma query. Nunca mezclar `TaxResult.casilla` con `Transaction.gross_amount`
para el mismo número visible — o todo por casilla o todo por transaction.

## No commitear sin revisar datos reales

**Patrón:** Arreglé el bug de cartera y fui directo a `git commit`. El usuario
abrió la web, vio otro desajuste (dividendos), y pidió parar.

**Regla:** Antes de commit+push de cualquier cambio que afecte números en
la UI, revisar la página en vivo (con `/browse` si aplica) y confirmar que
las tarjetas del dashboard y los desgloses cuadran numéricamente.
