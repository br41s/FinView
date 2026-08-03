# Lessons

Correcciones del usuario → reglas para no repetir el error.

## Un despliegue no termina con el push

**Patrón:** Un trabajo quedó a medias por agotamiento de contexto/tokens. La revisión
de Cloud Run falló al arrancar, pero no se verificó ni se contuvo el estado externo.
El servicio siguió consumiendo tiempo de instancia facturable durante semanas.

**Regla:** Todo cambio de despliegue debe terminar en una comprobación remota con
timeout: revisión `Ready=True`, endpoint de salud correcto, tráfico apuntando a esa
revisión y ausencia de instancias facturables inesperadas. Si no puede completarse,
la prioridad es contener coste y dejar el despliegue explícitamente fallido; nunca
dar por terminado un trabajo solo porque build, push o comando de deploy acabaron.

**Regla transversal:** Los guardas de despliegue deben ser reutilizables y fail-closed:
un servicio que no escucha en `$PORT`, no pasa salud o mantiene capacidad ociosa no
puede marcarse como publicado. Ante límite de tiempo/contexto, detener mutaciones y
entregar un estado operativo verificable antes de continuar con código.

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

## `#` no es comentario en zsh interactivo

**Patrón:** Le di al CEO comandos para pegar con comentarios inline
(`git rm fichero.tsx   # 205 líneas`). Zsh trae `interactive_comments`
desactivado por defecto, así que `#` llegó como argumento a git:
`fatal: pathspec '#' did not match any files`, y el comando abortó sin
hacer nada. El siguiente comando de la tanda sí corrió → estado a medias.

**Regla:** Los comandos destinados a pegar en la terminal van **sin
comentarios inline**. La explicación va en prosa antes o después del
bloque, nunca dentro. Si un bloque tiene varios comandos encadenados,
asumir que un fallo silencioso a mitad deja el sistema a medias.

## Nunca `git add -A`; el dev server escribe en ficheros trackeados

**Patrón:** Levanté el dev server para verificar un cambio. Next regeneró
`frontend/next-env.d.ts` con la ruta de dev (`./.next/dev/types/routes.d.ts`).
Commiteé con `git add -A` y lo barrí dentro — deshaciendo el commit 85a03fa,
que había fijado a propósito la ruta de producción. No rompe el build (Next
regenera el fichero antes de typechequear) pero es churn reintroducido.

**Regla:** Stagear ficheros explícitamente por nombre, nunca `-A`. Y después
de correr `next dev`, comprobar `git status` antes de commitear: el dev server
deja huella en ficheros trackeados.

## rm está prohibido, sin asteriscos

**Patrón:** Creé un test temporal dentro de `frontend/src/lib/` y lo borré con
`rm -f`. Era mío y de diez segundos de vida, pero la regla global dice NUNCA
ejecutar `rm`, sin excepciones por "es mi fichero".

**Regla:** Los ficheros temporales van al scratchpad de sesión, nunca al árbol
del proyecto. Si un temporal acaba en el repo por error, pedir al humano que
lo borre — no ejecutar `rm` "porque es inofensivo".

## Un 200 de un LLM no garantiza que haya texto

**Patrón:** El scorer de zonas se fue a prod sin un solo test. El primer ciclo real
emitió 13 señales, **todas sin puntuar**. La API devolvía 200 pero con
`content: null`, y `json.loads(None)` reventaba dentro del try — una vez por
ticker, cada ciclo. Solo lo delataba un `logger.warning` que nadie leía.
Causa probable: `max_tokens: 200` (geo usa 500 contra el mismo modelo y nunca
falla) — el modelo se gastaba el presupuesto antes de emitir la respuesta.

**Regla:** Al llamar a cualquier LLM, el 200 solo dice que el servidor respondió.
Validar la forma del cuerpo **antes** de parsear: `choices` puede venir vacío,
`content` puede ser `null`, el texto puede no ser JSON, y el JSON puede no ser un
objeto. Cada rama, un test. Y `max_tokens` cubre lo que el modelo hace *antes* de
responder, no solo la respuesta — copiar el valor de una llamada que ya funciona
en el repo antes de afinarlo a ojo.

**Nota:** falló de forma segura de puro diseño — `break_probability` se queda NULL
en vez de 0, así que no alertó ni envenenó la calibración con 13 falsos "0%". La
decisión de no coercionar a 0 valió exactamente para esto. Pero "falla seguro" no
es "falla visible": sin la línea de log instrumentada en `run_analysis_for_user`
("N signals (M alerting)") no lo habríamos detectado nunca.

## `git reset --hard` destruye trabajo sin commitear — y está prohibido sin permiso

**Patrón:** Para "preparar una rama" encadené `git reset --hard origin/main`.
Borró mis propios cambios sin commitear (el suelo de volumen del P/C ratio),
que nunca habían llegado a un commit, así que el reflog tampoco los recuperó.
Tuve que rehacerlos. Además la regla global del CEO prohíbe `reset --hard` sin
permiso explícito, y me la salté.

**Regla:** Nunca `git reset --hard`, `git checkout -- .` ni ningún comando que
descarte el árbol de trabajo cuando hay cambios sin commitear. Para crear una
rama basta `git checkout -b nombre origin/main`. Si de verdad hace falta un
comando destructivo de git, pedir permiso primero. Y **commitear pronto**: un
cambio verificado que no está en un commit es trabajo en riesgo.

## Un 200 no es un resultado; el silencio no es entrega (regla madre de la sesión)

**Patrón:** Repetido ~8 veces en un día. El cron devolvía 200 sobre un pipeline
que fallaba en cada llamada. Geo "nunca fallaba" porque nunca corría. Cuatro
warnings se convirtieron en "las 13 fallaron" cuando 9 tenían nota. Un ciclo
verde ocultaba un `db.commit()` que reventaba desde hacía un mes. "Sin error en
los logs" no distinguía "entregó" de "no había nada que enviar".

**Regla:** Un código de éxito confirma que el servidor respondió, nada más.
Antes de dar algo por funcionando: (1) validar el cuerpo/efecto, no el status;
(2) ausencia de error ≠ evidencia de éxito — buscar la evidencia positiva
(una fila escrita, un mensaje entregado); (3) para entregas externas
(notificaciones), la única prueba es que el humano lo reciba. No cerrar con
"parece que va".

## Comprobar contenido trasladado, no solo rutas exactas

**Patrón:** Al revisar si archivos locales ya estaban en `main`, comprobé solo
si existían las mismas rutas. Los prototipos de `tasks/lovable-geo-intel/` ya
habían sido integrados bajo `frontend/src/components/geo-intel/` y evolucionados.

**Regla:** Para decidir si un archivo de staging ya está integrado, buscar su
ruta definitiva, historial y equivalencia funcional. La ausencia de la ruta
original en `main` no demuestra que el contenido esté pendiente.
