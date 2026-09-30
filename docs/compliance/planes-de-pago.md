# Cláusulas para cuando haya planes de pago

FinView **no se vende hoy**: no hay cuenta de Stripe y las condiciones publicadas dicen que
el servicio es gratuito. Este borrador conserva las cláusulas de contratación que harían
falta el día que se active el cobro. No está publicado ni es vinculante.

Antes de activar pagos:

1. Volver a incluir estas cláusulas en `frontend/src/app/legal/condiciones/page.mdx`,
   renumerando, y devolver el título a "Condiciones de uso y contratación".
2. Añadir a Stripe a `PROCESSORS` (`frontend/src/lib/legal.ts`), a la política de privacidad
   (datos de suscripción, base jurídica de cobro, conservación de justificantes) y a la
   política de cookies (Stripe usa cookies propias en su página de pago).
3. Recuperar en `/legal/condiciones` el tope de responsabilidad y los reembolsos
   proporcionales por baja o retirada de funciones.
4. Comprobar en Stripe que los precios incluyen impuestos y que la cancelación se aplica al
   final del periodo, que es lo que afirman las cláusulas.
5. Subir `TERMS_VERSION` para que todos los usuarios acepten la nueva versión.
6. Quitar de `/pricing` el aviso de que los planes de pago no están a la venta.

Como titular es una LLC de Nuevo México que vende a consumidores de la UE, revisar también
con un asesor el IVA de servicios digitales (ventanilla única) antes del primer cobro.

---

## 5. Planes y precios

| Plan | Precio | Cuentas de bróker | Importaciones al mes |
|---|---|---|---|
| Gratis | 0 € | Hasta 2 | Hasta 5 |
| Pro | 9,99 € al mes | Hasta 10 | Hasta 50 |
| Unlimited | 19,99 € al mes | Sin límite | Sin límite |

Las funciones de la aplicación son las mismas en todos los planes; lo que cambia es el número de cuentas de bróker e importaciones mensuales. Volver a subir un archivo ya importado no consume importaciones.

Los precios son finales e incluyen los impuestos aplicables. Los precios vigentes son siempre los publicados en la página de [Precios](/pricing) en el momento de contratar.

## 6. Contratación, pago y renovación

1. Eliges un plan en la página de Precios con tu sesión iniciada.
2. Se te redirige a la pasarela de pago de Stripe, donde revisas el importe e introduces el medio de pago. Hasta que confirmas el pago puedes corregir cualquier dato o abandonar el proceso.
3. Al confirmarse el pago, el plan se activa de inmediato y Stripe te envía el justificante por email.

El contrato se formaliza en español. El titular no archiva un documento contractual individual; estas condiciones están siempre disponibles en esta página.

La suscripción es **mensual y se renueva automáticamente** cada mes por el precio vigente hasta que la canceles. Si un cobro falla, el plan puede quedar suspendido y tu cuenta pasar al plan Gratis hasta que regularices el pago.

Si modificamos el precio de tu plan te avisaremos con al menos 30 días de antelación; podrás cancelar antes de que se aplique.

## 7. Cancelación

Puedes cancelar tu suscripción en cualquier momento, sin permanencia ni penalización, desde *Facturación › Gestionar suscripción*. La cancelación surte efecto al final del periodo ya pagado: hasta entonces conservas el plan, y después tu cuenta pasa al plan Gratis. No se reembolsan periodos parciales, salvo lo previsto en el apartado 8 y en la ley.

Al pasar al plan Gratis no se borra ningún dato. Si superas los límites del plan Gratis conservarás lo que ya tienes, pero no podrás añadir nuevas cuentas o importaciones hasta volver a estar dentro del límite.

## 8. Derecho de desistimiento

Si contratas como consumidor, tienes derecho a desistir del contrato **durante 14 días naturales** desde la contratación del plan de pago, sin necesidad de justificación (artículos 102 y siguientes del texto refundido de la Ley General para la Defensa de los Consumidores y Usuarios).

Para ejercerlo, envíanos antes de que venza el plazo una declaración inequívoca a <a href={`mailto:$hola@biglobster.top`}>hola@biglobster.top</a> desde el email de tu cuenta. Puedes usar este modelo, aunque no es obligatorio:

> A la atención de Biglobster LLC (hola@biglobster.top): por la presente comunico que desisto del contrato de suscripción al plan [Pro / Unlimited] de FinView, contratado el [fecha]. Nombre: [tu nombre]. Email de la cuenta: [tu email]. Fecha: [fecha].

Te devolveremos **el importe íntegro** pagado, por el mismo medio de pago, en un plazo máximo de 14 días naturales desde que recibamos tu comunicación, y tu cuenta pasará al plan Gratis.

