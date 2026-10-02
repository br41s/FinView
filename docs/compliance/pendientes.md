# Pendientes que no resuelve el código

Estado a 2026-10-02. Ordenado por importancia.

## Resuelto

- [x] Datos del titular: Biglobster LLC, tomados de biglobster.top.
- [x] Buzón de contacto: hola@biglobster.top (el anterior `hola@finview.app` no existía).
- [x] Pagos: no hay. Los documentos describen un servicio gratuito.

## Decidido por el titular

Decisiones de Biglobster LLC, registradas con su fecha. No son pendientes: se anotan aquí
con lo que implican para que quien revise el cumplimiento sepa que fueron elecciones.

- [x] **Ideas es interpretación de datos, no asesoramiento financiero (2026-10-02).** La
      sección relaciona eventos públicos con los activos que históricamente se han movido con
      ellos, mediante reglas escritas y, cuando ninguna aplica, un modelo de lenguaje. El
      instrumento y el sentido (alcista o bajista) describen esa relación; no son una
      recomendación ni un pronóstico. Así lo dicen `/legal/condiciones` §3, el aviso de la
      cabecera de Ideas y el de cada señal, y la regla común de los prompts
      (`backend/services/llm_rules.py`). La sección conserva el nombre "Ideas".
      Qué mantiene esta postura cierta: que ninguna pantalla, prompt o notificación diga qué
      comprar o vender, cuánto, dónde ni cómo. Si el producto empezara a hacerlo, o a cobrar
      por las señales, la calificación habría que revisarla con un abogado (Reglamento de
      Abuso de Mercado, art. 3.1.35; MiFID II).
- [x] **Representante en la Unión: misma solución que biglobster.top (2026-10-02).** No se
      designa un representante del art. 27 RGPD. La política de privacidad hace lo mismo que
      la de biglobster.top: declara que el RGPD se aplica por el art. 3.2 aunque el
      responsable esté fuera de la Unión, da un contacto directo para protección de datos,
      aplica el estándar más protector cuando concurren varias normas, remite a la autoridad
      de control del país de residencia (en España la AEPD) y, en su caso, a la de Tailandia,
      declara el acceso del personal del responsable desde Tailandia como transferencia
      internacional con cláusulas contractuales tipo, y lleva un registro de versiones.
      Lo que esta solución no hace: no nombra a nadie establecido en la UE como punto de
      contacto. Si una autoridad lo exigiera, o el servicio creciera, designar uno es un
      trámite con un proveedor de representación y un cambio de una línea en la política.

## Para revisar con un abogado

- [ ] **Ley de Nuevo México frente a consumidores de la UE.** Las condiciones copian la
      cláusula de biglobster.top: ley de Nuevo México, sin privar al consumidor de las
      normas imperativas de su país. Confirmar que es la elección deseada para FinView.
- [ ] **Evaluación de impacto (art. 35).** No parece obligatoria a esta escala; confirmarlo.

## Decisiones de producto

- [ ] **`/pricing` sigue mostrando Pro (9,99 €) y Unlimited (19,99 €)** con sus botones,
      que hoy solo llevan al registro gratuito. Se añadió un aviso de que no están a la
      venta. Si no se va a vender, lo coherente es retirar esas dos tarjetas o marcarlas
      como "Próximamente"; no se ha hecho porque cambia la página de forma visible.
- [ ] La página `/billing` se llama "Facturación" y ofrece "Mejorar plan". Los documentos
      remiten a *Facturación › Cuenta* para descargar y borrar datos. Renombrarla a "Cuenta"
      sería más claro.

## Proveedores

- [ ] Aceptar o descargar el DPA de **Neon** y de **Vercel** y guardar constancia.
- [ ] **OpenRouter y el modelo.** El modelo por defecto es `deepseek/deepseek-v4-flash`.
      OpenRouter decide qué proveedor lo sirve, que puede estar fuera del EEE y de EE. UU.
      Los prompts no llevan identidad, pero el asistente envía texto libre del usuario.
      Opciones: restringir el enrutado a proveedores sin retención de datos
      (`provider.data_collection: "deny"` en la petición), o cambiar de modelo. No se ha
      tocado porque puede dejar el modelo sin proveedor; hay que probarlo contra la API real.
- [ ] Confirmar la retención de copias de **Neon**. La política de privacidad dice "máximo
      30 días".

## Mejoras técnicas que reforzarían el cumplimiento

- [ ] Verificación de email y recuperación de contraseña (hoy no existen; un usuario que
      olvida la contraseña no puede borrar su cuenta por sí mismo y tendría que pedirlo por
      email).
- [ ] Retención de `options_snapshots`: no se purgan nunca.
- [ ] Turnstile en el registro (hoy solo en el acceso).

## Si algún día se vende

Seguir `planes-de-pago.md`. Añade, además de lo que allí se lista, el IVA de servicios
digitales a consumidores de la UE para un vendedor estadounidense.
