# Pendientes que no resuelve el código

Estado a 2026-10-02. Ordenado por importancia.

## Resuelto

- [x] Datos del titular: Biglobster LLC, tomados de biglobster.top.
- [x] Buzón de contacto: hola@biglobster.top (el anterior `hola@finview.app` no existía).
- [x] Pagos: no hay. Los documentos describen un servicio gratuito.

## Para revisar con un abogado

- [ ] **Representante en la Unión (art. 27 RGPD).** Un responsable sin establecimiento en
      la UE que ofrece servicios a personas en la UE debe designar un representante, salvo
      que el tratamiento sea ocasional, no incluya a gran escala categorías especiales y sea
      improbable que entrañe riesgo. FinView trata de forma continuada datos financieros y
      fiscales y, si el usuario lo indica, un dato de salud. No se ha designado ninguno y la
      política de privacidad no lo menciona. Es la cuestión abierta más clara.
- [ ] **Señales e "Ideas" frente a la normativa de mercados.** Postura del titular
      (2026-10-02): FinView muestra datos, no presta asesoramiento, y la decisión de invertir
      es del usuario. Hecho en producto: esa frase figura en el pie público, en el registro
      (casilla), en el aviso de reaceptación, en la cabecera de Opciones, Zonas Clave e Ideas
      y junto a cada texto generado por IA; "Top Picks" pasa a "Tickers con más actividad";
      el subtítulo de Ideas ya no habla de "oportunidades de inversión y especulación"; todos
      los prompts llevan una regla que prohíbe recomendar comprar, vender o dimensionar; las
      tasas de acierto llevan "los aciertos pasados no garantizan resultados futuros".
      Sigue abierto para un abogado: un aviso no cambia la naturaleza de lo que se difunde.
      Ideas sigue mostrando instrumento y dirección (alcista/bajista) por evento, y eso puede
      ser "recomendación de inversión" del art. 3.1.35 del Reglamento de Abuso de Mercado
      aunque el servicio sea gratuito. La sección conserva el nombre "Ideas".
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
