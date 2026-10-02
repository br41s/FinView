# Cumplimiento — documentación interna

Documentación interna de cumplimiento de FinView. **No se publica**: los documentos
públicos viven en `frontend/src/app/legal/` y leen sus datos de `frontend/src/lib/legal.ts`.

Nada de lo que hay aquí es asesoramiento jurídico. Es el estado real del producto descrito
con el rigor suficiente para que un abogado lo revise sin tener que leer el código.

| Documento | Para qué |
|---|---|
| [registro-actividades.md](registro-actividades.md) | Registro de actividades de tratamiento (art. 30 RGPD), subencargados y plazos de conservación |
| [brechas.md](brechas.md) | Qué hacer ante una brecha de seguridad (arts. 33-34 RGPD) |
| [pendientes.md](pendientes.md) | Lo que solo puede hacer el titular y lo que debe revisar un abogado |
| [planes-de-pago.md](planes-de-pago.md) | Borrador de cláusulas de contratación para el día que se active el cobro |

## Titular y modelo

El titular es **Biglobster LLC** (Nuevo México, EE. UU.; registro 3279115, Entity ID
0008120949), con los mismos datos que publica en biglobster.top. **FinView no se vende**: no
hay cuenta de Stripe, las condiciones dicen que el servicio es gratuito y `/pricing` avisa de
que los planes Pro y Unlimited no están a la venta. El código de Stripe sigue en el backend,
inactivo sin claves. El RGPD se aplica por el art. 3.2 (servicio ofrecido en español a
personas en la UE), aunque el responsable esté fuera de la Unión. El personal del titular
opera el servicio desde Tailandia, y la política lo declara como transferencia internacional.

## Mapa normativo

| Norma | Qué exige aquí | Dónde se cumple |
|---|---|---|
| RGPD arts. 13-14 · LOPDGDD | Informar del tratamiento | `/legal/privacidad` |
| RGPD art. 3.2 y art. 27 | El RGPD se aplica a un responsable de fuera de la UE; representante en la Unión | `/legal/privacidad` §1 y §7. Misma solución que biglobster.top: sin representante designado, contacto directo, estándar más protector, autoridades de control, transferencia a Tailandia declarada. Ver `pendientes.md` |
| RGPD arts. 44-46 | Garantías para transferencias fuera del EEE | Tabla de destinatarios (`PROCESSORS`) y `/legal/privacidad` §7: DPF o cláusulas tipo por proveedor; acceso del titular desde Tailandia con cláusulas tipo |
| RGPD art. 7.1 | Poder demostrar el consentimiento | `users.terms_version`, `users.terms_accepted_at`; casilla sin premarcar en `/register` |
| RGPD art. 9.2.a | Consentimiento explícito para datos de salud | `fiscal_profiles.health_data_consent_at`; casilla junto al campo de discapacidad |
| RGPD arts. 15 y 20 | Acceso y portabilidad | `GET /api/users/me/export` |
| RGPD art. 17 | Supresión | `POST /api/users/me/delete` |
| RGPD art. 28 | Contrato con encargados | Lista en `lib/legal.ts` → `PROCESSORS`; DPA de cada proveedor (ver pendientes) |
| RGPD art. 30 | Registro de actividades | `registro-actividades.md` |
| RGPD arts. 33-34 | Notificación de brechas | `brechas.md` |
| LSSI-CE art. 10 (en lo aplicable a un prestador no establecido en España) | Identificar al titular | `/legal/aviso-legal` |
| LSSI-CE art. 22.2 | Informar de cookies; consentimiento si no son técnicas | `/legal/cookies`. Solo hay cookies técnicas: no hace falta banner |
| TRLGDCU arts. 60, 97, 102-108 | Información precontractual, precio final, desistimiento | Hoy no aplica a una venta: el servicio es gratuito (`/legal/condiciones` §5). Cláusulas preparadas en `planes-de-pago.md` |
| Ley 6/2023 (mercados de valores) · MiFID II · MAR | No prestar asesoramiento ni difundir recomendaciones sin autorización | Postura: FinView muestra datos y no aconseja. `NOT_ADVICE` (`frontend/src/lib/legal.ts`) en pie público, registro, aviso de reaceptación, cabeceras y junto a cada texto de IA; `/legal/condiciones` §3 y `/legal/aviso-legal` §3; regla común en todos los prompts (`backend/services/llm_rules.py`, `test_llm_rules.py`). Ideas se define como interpretación de datos (`/legal/condiciones` §3) |
| Reglamento (UE) 2024/1689 (IA), art. 50 | Identificar el contenido generado por IA | `AiDisclaimer`; `/legal/privacidad` §4 |

## Reglas que mantienen esto cierto

- **Tabla nueva → clasificarla.** `backend/services/user_data.py` deriva del esquema qué
  tablas son del usuario (tienen `user_id` o una clave foránea hacia una que lo es). Una tabla
  que no lo sea debe añadirse a `GLOBAL_TABLES`. `test_user_data.py` falla si no está en
  ninguno de los dos grupos: así ninguna tabla queda fuera de la exportación ni del borrado.
- **Cambio en un documento legal → añadir una fila a su "Registro de versiones"**, al final
  de `/legal/privacidad` y `/legal/condiciones`, igual que en biglobster.top.
- **Cambio relevante en un documento legal → subir `TERMS_VERSION`** en
  `backend/services/auth_service.py` y `LEGAL_UPDATED` en `frontend/src/lib/legal.ts`. Todos
  los usuarios con otra versión ven el aviso de aceptación en el dashboard.
- **Proveedor nuevo que recibe datos de usuarios → añadirlo a `PROCESSORS`** y al registro
  de actividades en el mismo cambio. Una analítica o un píxel convierten la política de
  cookies en falsa y obligan a un banner de consentimiento.
- **El copy de `/pricing` y la tabla de `/legal/condiciones` §5 dicen lo que aplica
  `PLAN_LIMITS`.** Anunciar una función que no existe es publicidad engañosa.
- **Activar pagos no es solo poner claves de Stripe.** Antes hay que seguir la lista de
  `planes-de-pago.md`: condiciones de contratación, Stripe en `PROCESSORS` y en las
  políticas, y nueva versión de `TERMS_VERSION`.
- **Nada de lo que se muestra puede leerse como consejo.** Un prompt nuevo que genere texto
  visible importa la regla de `llm_rules.py`; una pantalla nueva con señales o texto de IA
  lleva `AiDisclaimer`; una tasa de acierto lleva `PastPerformanceNote`. No se nombran
  secciones como selección para invertir ni se indica dónde o cómo operar.
- **Lo que se envía al modelo de IA no lleva identidad.** Ni email, ni nombre, ni importes.
  Si un prompt nuevo los necesita, antes se actualiza la política de privacidad.
