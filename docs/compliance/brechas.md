# Brechas de seguridad (arts. 33-34 RGPD)

Una brecha es cualquier acceso, pérdida, alteración o divulgación no autorizada de datos
personales. No hace falta un ataque: un backup expuesto, un token filtrado en un log o un
fallo de aislamiento entre usuarios también lo son.

## Plazos

- **72 horas** desde que se tiene constancia para notificar a la autoridad de control, salvo
  que sea improbable que suponga un riesgo para los derechos de las personas. Biglobster LLC
  no tiene establecimiento en la UE, así que no hay autoridad principal: se notifica a la del
  país de los afectados, que para los usuarios de FinView es la AEPD.
- **Sin dilación** a los afectados cuando el riesgo sea alto. Los datos financieros y
  fiscales, y el dato de discapacidad, elevan el riesgo.

## Pasos

1. **Contener.** Rotar `FINVIEW_SECRET_KEY` y `FINVIEW_AUTH_SECRET` invalida todas las
   sesiones. Rotar la contraseña de Neon y la clave de OpenRouter si pudieron verse
   afectadas. Revocar el despliegue comprometido.
2. **Anotar la hora** en que se tuvo constancia: de ahí cuentan las 72 horas.
3. **Evaluar.** Qué datos, de cuántos usuarios, durante cuánto tiempo, si estaban cifrados,
   si hay indicios de uso. Fuentes: Cloud Logging (30 días), logs de Neon y Vercel.
4. **Notificar a la AEPD** por su sede electrónica (formulario de brechas de datos
   personales) con: naturaleza de la brecha, categorías y número aproximado de afectados y
   registros, consecuencias probables, medidas adoptadas y contacto.
5. **Comunicar a los afectados** si el riesgo es alto, en lenguaje claro: qué ha pasado,
   qué datos, qué hemos hecho y qué pueden hacer ellos. FinView no tiene proveedor de email
   transaccional: hoy la comunicación sería manual, desde el buzón de contacto.
6. **Registrar** la brecha aunque no se notifique (art. 33.5): hechos, efectos y medidas.
   Añadir una entrada a este archivo.

## Registro de brechas

Ninguna registrada.
