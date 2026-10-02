# Registro de actividades de tratamiento (art. 30 RGPD)

Responsable: Biglobster LLC, 1209 Mountain Road Pl NE Ste N, Albuquerque, NM 87110, Estados
Unidos (`LEGAL` en `frontend/src/lib/legal.ts`). Contacto: hola@biglobster.top.
Sin establecimiento en la UE; el RGPD se aplica por el art. 3.2.
Última revisión: 2026-10-02.

## Actividades

| # | Actividad | Finalidad | Base jurídica | Interesados | Datos | Conservación |
|---|---|---|---|---|---|---|
| 1 | Gestión de cuentas de usuario | Alta, acceso y mantenimiento de la cuenta | Contrato (6.1.b) | Usuarios | Email, nombre, hash de contraseña, versión y fecha de aceptación de condiciones | Hasta la eliminación de la cuenta |
| 2 | Importación y cálculo de cartera y fiscalidad | Prestar el servicio principal | Contrato (6.1.b) | Usuarios | Operaciones, dividendos, retenciones, posiciones, identificador de cuenta en el bróker, nombre y huella del archivo importado, resultados fiscales, lotes FIFO | Hasta que el usuario borre la importación, la cuenta de bróker o su cuenta |
| 3 | Perfil fiscal | Estimar la base del ahorro | Contrato (6.1.b); **discapacidad: consentimiento explícito (9.2.a)** | Usuarios | Edad, descendientes, base general, pérdidas pendientes, grado de discapacidad | Igual que 2; el consentimiento se retira poniendo el campo a "Ninguna" |
| 4 | Inversiones alternativas | Seguimiento de posiciones no cotizadas | Contrato (6.1.b) | Usuarios | Posiciones, importes, gestora, notas libres | Igual que 2 |
| 5 | Señales y análisis automáticos | Alertas de opciones, zonas clave, ideas | Contrato (6.1.b) | Usuarios | Listas de seguimiento, alertas, preguntas al asistente, salida del modelo | Igual que 2 |
| 6 | Seguridad del servicio | Anti-robots, límite de peticiones, registros técnicos | Interés legítimo (6.1.f) | Usuarios y visitantes | IP, fecha y hora, señales del navegador (Turnstile) | Registros: 30 días (retención por defecto de Cloud Logging) |
| 7 | Atención de solicitudes y derechos | Responder consultas y ejercicio de derechos | Obligación legal (6.1.c) | Usuarios | Email y contenido de la solicitud | El necesario para acreditar la respuesta |

No hay cobros: FinView es gratuito y no trata datos de pago. Las columnas de suscripción de
`users` existen pero están vacías salvo el plan `FREE`.

No hay decisiones automatizadas con efectos jurídicos (art. 22), ni elaboración de perfiles
comerciales, ni comunicaciones comerciales, ni analítica web.

## Encargados del tratamiento

La lista pública es `PROCESSORS` en `frontend/src/lib/legal.ts`; esta tabla añade lo que
hace falta para gestionarlos.

| Encargado | Servicio | Ubicación de los datos | Transferencia internacional | Contrato (DPA) |
|---|---|---|---|---|
| Biglobster LLC (personal autorizado) | Operación, mantenimiento y soporte | Acceso desde Tailandia a sistemas alojados en la UE | Sí — cláusulas contractuales tipo (art. 46.2.c); Tailandia no tiene decisión de adecuación | No aplica: es el propio responsable |
| Google Cloud EMEA Ltd | Cloud Run, Cloud Build, Cloud Logging | europe-west1 (Bélgica) | No | Cloud Data Processing Addendum, aceptado con los términos de la cuenta |
| Neon, Inc. | Postgres | eu-central-1 (Fráncfort) | Accesos de soporte desde EE. UU. | DPA de Neon — **comprobar que está aceptado** |
| Vercel Inc. | Frontend y proxy de `/api` | UE y EE. UU. | Sí — DPF y cláusulas tipo | DPA de Vercel — **comprobar que está aceptado** |
| Cloudflare, Inc. | Turnstile | UE y EE. UU. | Sí — DPF y cláusulas tipo | DPA de Cloudflare, incluido en sus condiciones |
| OpenRouter, Inc. + proveedor del modelo | LLM (`settings.openrouter_model`) | EE. UU. y otros | Sí | **Revisar**: ver `pendientes.md` |

El acceso del propio responsable desde Tailandia figura en la tabla y en `/legal/privacidad`
§6 y §7, con la misma redacción que usa biglobster.top.

Sin datos personales: Yahoo Finance (solo tickers/ISIN), BCE, FRED, CNMV, MEFF, Eurex,
GDELT, OFAC, Federal Register, NASA, USGS, GDACS, adsb.lol.

Canales de aviso del operador (ntfy.sh, Telegram, Gmail SMTP): reciben alertas de mercado
**sin ningún identificador de usuario**. `POST /options/test-telegram` enviaba el email del
usuario al chat del operador; se eliminó el 2026-09-30.

## Datos que no se conservan

- Los archivos de bróker subidos: se escriben en un temporal del contenedor, se procesan y
  se eliminan en el `finally` de cada endpoint de importación (`backend/api/imports.py`).
- Datos de pago: no se piden.

## Medidas de seguridad (art. 32)

TLS en todo el tráfico · contraseñas con bcrypt · JWT firmado, 90 días · aislamiento por
`user_id` en cada consulta · Turnstile en el acceso · límite de peticiones en acceso, registro
y borrado de cuenta · cabeceras de seguridad en todas las respuestas · secretos en variables
de entorno con arranque bloqueado si faltan en producción · borrado de cuenta con
confirmación por contraseña.

Detalle en `.claude/rules/auth-security.md`.
