import fs from 'node:fs';
import path from 'node:path';

/**
 * The blog index, and the check that keeps it honest.
 *
 * An article is a directory under `app/blog/` holding a `page.mdx`; the card
 * that links to it is an entry here. Nothing connected the two, so both halves
 * had drifted: two cards pointed at directories that never existed (a 404 from
 * the index, live in production), and two articles had no card at all and were
 * reachable only by knowing the URL. `blogPosts()` now refuses to build when the
 * two sets disagree, in either direction.
 *
 * Card copy is deliberately NOT derived from each article's `metadata` export.
 * They serve different readers: the MDX title is the `<title>` tag, kept under
 * ~60 characters for search results, while the card title is free to be longer
 * and more descriptive. 16 of 60 genuinely differ today, and the excerpt differs
 * from the meta description in 48 of 60. Deriving one from the other would
 * quietly rewrite the index every time someone tuned a title for SEO.
 */

/**
 * A closed set, so a sixth spelling cannot appear by typo.
 *
 * 'Fiscal' (22 posts) and 'Fiscalidad' (9) are the same category under two
 * names — nothing renders them differently. Left alone here because merging
 * them relabels nine cards, which is an editorial call, not a refactor.
 */
export type PostTag = 'Brokers' | 'Estrategia' | 'Fiscal' | 'Fiscalidad' | 'Métricas';

export type PostMeta = {
  slug: string;
  tag: PostTag;
  date: string;
  readTime: string;
  title: string;
  excerpt: string;
};

/**
 * Newest first is the rendered order, but it comes from `date` rather than from
 * where an entry happens to sit here — five posts had drifted out of order.
 * The sort is stable, so posts sharing a date keep the order below.
 */
export const POST_META = [
  {
    slug: 'inversiones-exteriores-d6-espana',
    tag: 'Fiscalidad',
    date: '4 oct 2026',
    readTime: '9 min',
    title: 'Inversiones exteriores: el D-6 ya no existe y esto es lo que sí te obliga',
    excerpt:
      'El D-6 desapareció con el Real Decreto 571/2023 y con él la obligación de declarar las carteras de valores. Lo que de verdad sigue vivo es el Modelo 720: dos trámites distintos que la gente confunde sin parar.',
  },
  {
    slug: 'metodo-fifo-irpf-espana',
    tag: 'Fiscalidad',
    date: '4 oct 2026',
    readTime: '11 min',
    title: 'El método FIFO en el IRPF: cómo empareja Hacienda tus compras y ventas',
    excerpt:
      'Tu broker te muestra un precio medio; Hacienda aplica FIFO y da por vendidas siempre tus acciones más antiguas. Cómo se calcula lote a lote, por qué cruza todos tus brokers y qué pasa con splits, herencias y acciones fraccionadas.',
  },
  {
    slug: 'sucesiones-acciones-eeuu-espana',
    tag: 'Fiscalidad',
    date: '2 oct 2026',
    readTime: '11 min',
    title: 'Impuesto de sucesiones de EEUU: la factura oculta de tus acciones americanas',
    excerpt:
      'Si tus acciones de empresas de EEUU superan los 60.000 $, tus herederos pueden pagar hasta el 40 % al IRS. Y no hay convenio con España, así que el impuesto de sucesiones español se suma. Cómo funciona el 706-NA y por qué los ETFs americanos no te libran.',
  },
  {
    slug: 'dividendos-colombianos-espana',
    tag: 'Fiscalidad',
    date: '1 oct 2026',
    readTime: '11 min',
    title: 'Dividendos colombianos en España: el 5 % del convenio y la devolución a la DIAN',
    excerpt:
      'Colombia retiene el 20 % del dividendo —y hasta el 48 % si sale de beneficios gravados—, pero el convenio de 2005 lo limita al 5 %. La trampa: Colombia no lo aplica en origen, así que el exceso se reclama a la DIAN y solo durante cinco años.',
  },
  {
    slug: 'dividendos-sudafricanos-espana',
    tag: 'Fiscalidad',
    date: '30 sep 2026',
    readTime: '11 min',
    title: 'Dividendos sudafricanos en España: el 20 % retenido y el 15 % del convenio',
    excerpt:
      'Sudáfrica retiene el 20 % del dividendo a un residente español y el convenio de 2006 lo limita al 15 %. Pero el exceso no se reclama al fisco sudafricano: lo devuelve quien te lo retuvo y solo durante tres años.',
  },
  {
    slug: 'dividendos-indios-espana',
    tag: 'Fiscalidad',
    date: '29 sep 2026',
    readTime: '11 min',
    title: 'Dividendos indios en España: el 20,8 % retenido y el techo del 15 %',
    excerpt:
      'La India pasó a gravar el dividendo en 2020 y hoy retiene un 20,8 % a un residente español, aunque el convenio de 1993 lo limita al 15 %. Cómo conseguir el tipo reducido y por qué la devolución exige un PAN y una declaración de la renta.',
  },
  {
    slug: 'dividendos-israelies-espana',
    tag: 'Fiscalidad',
    date: '28 sep 2026',
    readTime: '11 min',
    title: 'Dividendos israelíes en España: recuperar 15 puntos de un tope del 10 %',
    excerpt:
      'Israel retiene el 25 % del dividendo a un residente español, pero el convenio de 1999 limita el impuesto al 10 %. Cómo pedir el tipo reducido en origen y cómo reclamar el exceso al fisco israelí antes de que pasen los seis años.',
  },
  {
    slug: 'dividendos-chilenos-espana',
    tag: 'Fiscalidad',
    date: '27 sep 2026',
    readTime: '11 min',
    title: 'Dividendos chilenos en España: el 35 % que el convenio no te deja recuperar',
    excerpt:
      'Chile retiene el 35 % del dividendo a un residente español y el convenio de 2003 no lo limita: una excepción en su artículo 10 deja el impuesto adicional sin tope. Qué deduces en el IRPF con el artículo 80 y qué parte se pierde por el camino.',
  },
  {
    slug: 'dividendos-surcoreanos-espana',
    tag: 'Fiscalidad',
    date: '27 sep 2026',
    readTime: '10 min',
    title: 'Dividendos surcoreanos en España: cómo recuperar el 7 % retenido de más',
    excerpt:
      'Corea del Sur retiene el 22 % de tus dividendos, pero el convenio de 1994 limita el impuesto al 15 %. Desde 2024 el alivio en origen está cerrado para la vía minorista, así que la única puerta es reclamar. Cómo declarar el bruto y pedir la devolución al National Tax Service.',
  },
  {
    slug: 'dividendos-polacos-espana',
    tag: 'Fiscalidad',
    date: '25 sep 2026',
    readTime: '10 min',
    title: 'Dividendos polacos en España: cómo recuperar el 4 % retenido de más',
    excerpt:
      'Polonia retiene el 19 % de tus dividendos, pero el convenio de 1979 limita el impuesto al 15 %. Cómo declarar el bruto en el IRPF con la deducción del artículo 80 y cómo reclamar el exceso a la administración polaca.',
  },
  {
    slug: 'dividendos-japoneses-espana',
    tag: 'Fiscalidad',
    date: '24 sep 2026',
    readTime: '10 min',
    title: 'Dividendos japoneses en España: cómo recuperar el 15,42 % retenido de más',
    excerpt:
      'Japón retiene el 20,42 % de tus dividendos, pero el convenio de 2018 limita el impuesto al 5 %. Cómo declarar el bruto en el IRPF y cómo reclamar el exceso a la Agencia Tributaria japonesa.',
  },
  {
    slug: 'rsu-stock-options-irpf-espana',
    tag: 'Fiscalidad',
    date: '22 sep 2026',
    readTime: '11 min',
    title: 'RSUs y stock options: cómo tributan las acciones que te da tu empresa',
    excerpt:
      'El vesting tributa como nómina en la base general y la venta como plusvalía en la del ahorro. El precio de adquisición es el valor del día que consolidaste, no cero. La exención de 12.000 € y el sell to cover, explicados.',
  },
  {
    slug: 'dividendos-austriacos-espana',
    tag: 'Fiscalidad',
    date: '21 sep 2026',
    readTime: '10 min',
    title: 'Dividendos austriacos en España: cómo recuperar el 12,5 % retenido de más',
    excerpt:
      'Austria retiene el 27,5 % de tus dividendos, pero el convenio con España limita el impuesto al 15 %. Cómo declarar el bruto en el IRPF y cómo reclamar el exceso al Finanzamt con el trámite DIAG.',
  },
  {
    slug: 'dividendos-finlandeses-espana',
    tag: 'Fiscalidad',
    date: '20 sep 2026',
    readTime: '10 min',
    title: 'Dividendos finlandeses en España: cómo recuperar el 30 % retenido',
    excerpt:
      'Finlandia retiene el 30 % de tus dividendos y hasta el 35 % si la acción va a nombre de un intermediario. El convenio limita el impuesto al 15 %. Cómo declarar el bruto en el IRPF y cómo reclamar el exceso a la Verohallinto con el 6164e.',
  },
  {
    slug: 'dividendos-suecos-espana',
    tag: 'Fiscalidad',
    date: '19 sep 2026',
    readTime: '10 min',
    title: 'Dividendos suecos en España: cómo recuperar el 30 % retenido',
    excerpt:
      'Suecia retiene el 30 % de tus dividendos, pero el convenio de 1976 limita el impuesto al 15 %. Cómo declarar el bruto en el IRPF y cómo reclamar el exceso a Skatteverket con el SKV 3740 antes de que pasen los cinco años.',
  },
  {
    slug: 'dividendos-portugueses-espana',
    tag: 'Fiscalidad',
    date: '18 sep 2026',
    readTime: '10 min',
    title: 'Dividendos portugueses en España: cómo recuperar el 28 % retenido',
    excerpt:
      'Portugal retiene el 28 % de tus dividendos, pero el convenio limita el impuesto al 15 %. Cómo pedir la reducción en origen con el modelo 21-RFI y cómo reclamar el exceso con el 22-RFI antes de que caduque el plazo.',
  },
  {
    slug: 'dividendos-irlandeses-espana',
    tag: 'Fiscalidad',
    date: '17 sep 2026',
    readTime: '10 min',
    title: 'Dividendos irlandeses en España: cómo recuperar el 25 % y qué pasa con los ETF',
    excerpt:
      'Irlanda retiene el 25 % de los dividendos que paga a no residentes, pero un residente en España puede cobrar sin retención con el formulario V2A. Cómo declararlo, cómo reclamar el exceso y por qué un ETF irlandés no tiene nada que recuperar.',
  },
  {
    slug: 'dividendos-noruegos-espana',
    tag: 'Fiscalidad',
    date: '16 sep 2026',
    readTime: '10 min',
    title: 'Dividendos noruegos en España: cómo recuperar el 25 % retenido',
    excerpt: 'Noruega retiene el 25 % de tus dividendos, pero el convenio con España limita la retención al 15 %. Cómo declarar el bruto en el IRPF y pedir la devolución del exceso a Skatteetaten.',
  },
  {
    slug: 'dividendos-daneses-espana',
    tag: 'Fiscalidad',
    date: '14 sep 2026',
    readTime: '10 min',
    title: 'Dividendos daneses en España: cómo recuperar la retención',
    excerpt: 'Dinamarca puede retener el 27 % de tus dividendos. Qué dice Hacienda, cómo declararlos en España y cómo pedir la devolución a Skattestyrelsen.',
  },
  {
    slug: 'dividendos-australianos-espana',
    tag: 'Fiscalidad',
    date: '12 sep 2026',
    readTime: '9 min',
    title: 'Dividendos australianos en España: franked, unfranked y el crédito que no cobras',
    excerpt: 'Australia no retiene el dividendo franked a los no residentes, pero tampoco te deja recuperar el franking credit. Cómo distinguirlo del dividendo unfranked y declararlo bien en España.',
  },
  {
    slug: 'dividendos-canadienses-espana',
    tag: 'Fiscalidad',
    date: '11 sep 2026',
    readTime: '10 min',
    title: 'Dividendos canadienses en España: cómo evitar el 25 % de retención',
    excerpt: 'Canadá aplica un 25 % a los dividendos de no residentes, pero el convenio con España limita la retención al 15 %. Cómo revisar el NR301 y declarar el bruto en el IRPF.',
  },
  {
    slug: 'dividendos-neerlandeses-espana',
    tag: 'Fiscalidad',
    date: '10 sep 2026',
    readTime: '9 min',
    title: 'Dividendos neerlandeses en España: cómo declararlos',
    excerpt: 'Países Bajos suele retener el 15 % de tus dividendos. Cómo declarar el bruto en España, revisar el certificado del broker y reclamar si te han cobrado de más.',
  },
  {
    slug: 'dividendos-belgas-espana',
    tag: 'Fiscalidad',
    date: '09 sep 2026',
    readTime: '11 min',
    title: 'Dividendos belgas en España: cómo recuperar la retención de más',
    excerpt: 'Bélgica puede retener el 30 % de tus dividendos. Cómo declarar el bruto en España y pedir la devolución del exceso con el formulario 276DIV.',
  },
  {
    slug: 'dividendos-suizos-espana',
    tag: 'Fiscalidad',
    date: '06 sep 2026',
    readTime: '9 min',
    title: 'Dividendos suizos en España: cómo recuperar el 20 % retenido de más',
    excerpt: 'Suiza retiene el 35 % de los dividendos, pero el convenio con España limita la retención al 15 %. Cómo declarar el bruto y pedir la devolución del exceso.',
  },
  {
    slug: 'dividendos-britanicos-espana',
    tag: 'Fiscalidad',
    date: '06 sep 2026',
    readTime: '10 min',
    title: 'Dividendos británicos en España: el 0 % de retención tiene una excepción',
    excerpt: 'Las acciones británicas suelen pagar sin retención, pero los REIT pueden descontar por sus PID. Cómo distinguir ambos cobros y reclamar el exceso a HMRC.',
  },
  {
    slug: 'acciones-fraccionadas-irpf-espana',
    tag: 'Fiscalidad',
    date: '04 sep 2026',
    readTime: '10 min',
    title: 'Acciones fraccionadas en España: cómo tributan en el IRPF',
    excerpt: 'Comprar 0,17 acciones no cambia las reglas de Hacienda. Cómo distinguir una acción real de un derivado, aplicar FIFO, declarar dividendos y revisar el Modelo 720.',
  },
  {
    slug: 'dividendos-italianos-espana',
    tag: 'Fiscalidad',
    date: '03 sep 2026',
    readTime: '9 min',
    title: 'Dividendos italianos en España: cómo recuperar la retención',
    excerpt: 'Italia puede retener un 26 % de tus dividendos. Cómo declarar el bruto, aplicar la deducción en España y reclamar el exceso sobre el 15 % mediante el Modelo A.',
  },
  {
    slug: 'dividendos-alemanes-espana',
    tag: 'Fiscalidad',
    date: '03 sep 2026',
    readTime: '10 min',
    title: 'Dividendos alemanes en España: cómo recuperar la retención',
    excerpt: 'Alemania puede retener el 26,375 % de tus dividendos. Cómo declarar el bruto, aplicar la deducción en España y reclamar el exceso del 15 % mediante el portal BOP.',
  },
  {
    slug: 'fiscalidad-crowdlending-p2p-20260902',
    tag: 'Fiscalidad',
    date: '02 sep 2026',
    readTime: '10 min',
    title: 'Fiscalidad del crowdlending y P2P en España: cómo declararlo',
    excerpt: 'Los intereses P2P tributan aunque nadie te retenga. Cómo declarar plataformas extranjeras, reinversiones, impagos y el posible Modelo 720 sin mezclar conceptos.',
  },
  {
    slug: 'trade-republic-renta-20260830',
    tag: 'Fiscalidad',
    date: '30 ago 2026',
    readTime: '10 min',
    title: 'Trade Republic y la Renta: cómo declarar dividendos e inversiones',
    excerpt: 'El cambio de IBAN alemán a español partió el año fiscal en dos. Cómo leer el informe de Trade Republic, revisar intereses y dividendos, y corregir ventas mal clasificadas.',
  },
  {
    slug: 'dividendos-franceses-espana',
    tag: 'Fiscal',
    date: '29 ago 2026',
    readTime: '10 min',
    title: 'Dividendos franceses en España: cómo recuperar la retención',
    excerpt: 'Francia puede retenerte más del 15 % permitido por convenio. Cómo declarar el dividendo, reclamar el exceso con los modelos 5000 y 5001 y no perder el plazo.',
  },
  {
    slug: 'modelo-718-grandes-fortunas',
    tag: 'Fiscal',
    date: '27 ago 2026',
    readTime: '10 min',
    title: 'Modelo 718 en 2026: la guía que necesita tu cartera cuando supera 3 millones',
    excerpt: 'Qué es el Modelo 718, quién debe presentarlo y cómo afecta a una cartera de acciones, ETFs y dividendos. La novedad de 2026, los tramos y la deducción del Patrimonio.',
  },
  {
    slug: 'prima-asistencia-junta-accionistas-irpf',
    tag: 'Fiscal',
    date: '25 ago 2026',
    readTime: '8 min',
    title: 'Prima de asistencia a juntas: cómo tributa en el IRPF',
    excerpt:
      'Ese pequeño pago por votar en una junta también tributa. Cómo declarar primas de asistencia, regalos en especie y pagos de brokers extranjeros sin duplicar datos.',
  },
  {
    slug: 'splits-fusiones-canje-acciones-irpf',
    tag: 'Fiscal',
    date: '21 ago 2026',
    readTime: '8 min',
    title: 'Splits, contrasplits y fusiones: qué le pasa a tu coste de adquisición en el IRPF',
    excerpt:
      'Un split no te hace más rico, pero te rompe el coste medio. Y un canje por fusión no siempre está exento. Cómo recalcular el coste de tus acciones tras splits, contrasplits, fusiones y spin-offs antes de que el FIFO arrastre el error.',
  },
  {
    slug: 'dividendos-vs-alquiler-fiscalidad',
    tag: 'Fiscal',
    date: '19 ago 2026',
    readTime: '9 min',
    title: 'Dividendos vs alquiler: por qué el mismo euro no tributa igual',
    excerpt:
      'Un dividendo y un alquiler de 1.000 € no pagan lo mismo en tu Renta. El dividendo va a la base del ahorro (19-30 %); el alquiler, a la renta general y a tu tipo marginal. Te explico la asimetría que nadie te cuenta.',
  },
  {
    slug: 'captura-dividendo-irpf-espana',
    tag: 'Fiscal',
    date: '18 ago 2026',
    readTime: '11 min',
    title: 'Captura de dividendo en España: la trampa fiscal que la hunde',
    excerpt: 'Compras antes del dividendo, cobras y vendes al día siguiente. En papel es dinero gratis; en la Renta española sale caro por la regla de los dos meses y el límite del 25% a la compensación. Te explico por qué no funciona aquí.',
  },
  {
    slug: 'dividendo-mensual',
    tag: 'Estrategia',
    date: '18 ago 2026',
    readTime: '9 min',
    title: 'Dividendo mensual: las acciones y ETFs que te pagan cada mes (y cómo tributan en España)',
    excerpt:
      'Casi todas las empresas reparten trimestralmente, pero un puñado de acciones y ETFs te ingresa dividendos 12 veces al año. Te enseño cuáles son reales, cuáles dejaron de serlo en 2026 y qué hace Hacienda con ese cobro mensual.',
  },
  {
    slug: 'reyes-del-dividendo',
    tag: 'Estrategia',
    date: '17 ago 2026',
    readTime: '9 min',
    title: 'Reyes del Dividendo (Dividend Kings): las empresas con 50 años subiendo el pago',
    excerpt:
      'Solo 57 empresas en el mundo han subido su dividendo cada año durante más de 50 años. Qué son los Dividend Kings, por qué importa medio siglo de disciplina y cómo tributan en España los que cotizan en EE. UU.',
  },
  {
    slug: 'mudarte-al-extranjero-cartera-dividendos',
    tag: 'Fiscalidad',
    date: '15 ago 2026',
    readTime: '9 min',
    title: 'Mudarte al extranjero con tu cartera de dividendos: lo que Hacienda decide por ti al cambiar de residencia',
    excerpt:
      'El día que dejas de residir en España, tu cartera cambia de régimen sin que toques un título. Los 183 días, la retención de dividendos como no residente, el exit tax y el modelo 720 que te persigue cinco años más. Todo lo que nadie te cuenta antes de mudarte.',
  },
  {
    slug: 'promediar-a-la-baja-dividendos',
    tag: 'Estrategia',
    date: '13 ago 2026',
    readTime: '8 min',
    title: 'Promediar a la baja en dividendos: la jugada que divide a los inversores',
    excerpt:
      'Bajar tu coste medio comprando más cuando el precio cae suena obvio. Pero promediar a la baja esconde una trampa: echar dinero bueno al malo. Te doy las señales para saber cuándo es ganga y cuándo es un negocio roto, con el detalle fiscal en España.',
  },
  {
    slug: 'cuando-vender-acciones-dividendos',
    tag: 'Estrategia',
    date: '12 ago 2026',
    readTime: '8 min',
    title: 'Cuándo vender una acción de dividendos: el lado que nadie te enseña',
    excerpt:
      'Toda la doctrina habla de comprar y aguantar. Nadie explica cuándo salir. Te doy las señales objetivas para vender una posición, el coste fiscal de hacerlo en España y por qué no vender también es una decisión.',
  },
  {
    slug: 'aportaciones-periodicas-dca-dividendos',
    tag: 'Estrategia',
    date: '11 ago 2026',
    readTime: '8 min',
    title: 'Aportaciones periódicas (DCA): la forma más simple de construir tu cartera de dividendos',
    excerpt:
      'Deja de esperar el momento perfecto y compra todos los meses, digas lo que digas. Cómo funciona el DCA, qué hace con tu yield on cost y el detalle fiscal que casi nadie cuenta: cada aportación es un lote con su coste.',
  },
  {
    slug: 'amortizar-hipoteca-vs-invertir',
    tag: 'Estrategia',
    date: '08 ago 2026',
    readTime: '9 min',
    title: 'Amortizar hipoteca o invertir en dividendos: cómo decidir con números',
    excerpt:
      'La pregunta que todo inversor con hipoteca se hace al tener dinero de sobra. Comparo la amortización anticipada con una cartera de dividendos: la rentabilidad garantizada de quitar deuda, el coste fiscal de la bolsa y el plan intermedio que casi nadie plantea.',
  },
  {
    slug: 'intereses-cuentas-remuneradas-depositos-irpf',
    tag: 'Fiscalidad',
    date: '07 ago 2026',
    readTime: '10 min',
    title: 'Cuentas remuneradas y depósitos: cuánto tributan tus intereses en el IRPF',
    excerpt:
      'El primer euro de interés tributa, y el banco ya te retiene el 19 %. Cómo funciona la retención, el lío del límite de 1.600 €, los regalos por domiciliar la nómina y el caso de los neobancos extranjeros.',
  },
  {
    slug: 'bonos-renta-fija-fiscalidad-irpf',
    tag: 'Fiscalidad',
    date: '05 ago 2026',
    readTime: '11 min',
    title: 'Bonos y renta fija: cómo tributan tus cupones en el IRPF',
    excerpt: 'La fiscalidad de los bonos en España no es como la de las acciones: el cupón y la venta van al mismo cajón del IRPF. Te explico con números cómo tributan tus intereses y qué cambia frente a los dividendos.',
  },
  {
    slug: 'sociedad-patrimonial-dividendos-espana',
    tag: 'Fiscalidad',
    date: '04 ago 2026',
    readTime: '9 min',
    title: 'Sociedad patrimonial para invertir en dividendos: cuándo compensa y cuándo no',
    excerpt:
      'El 25% del Impuesto sobre Sociedades suena mejor que el IRPF hasta que sumas el segundo peaje al repartir, los costes anuales de la S.L. y descubres que la exención del 95% pide un 5% del capital que nunca vas a tener.',
  },
  {
    slug: 'cuentas-conjuntas-titularidad-dividendos-irpf',
    tag: 'Fiscalidad',
    date: '02 ago 2026',
    readTime: '8 min',
    title: 'Cuentas conjuntas y titularidad: quién declara los dividendos en el IRPF',
    excerpt:
      'Tener la cuenta del broker a nombre de dos personas no es un detalle administrativo. Gananciales, presunción del 50/50, retenciones mal imputadas, cuentas de menores y usufructo: quién declara qué y con qué prueba.',
  },
  {
    slug: 'riesgo-divisa-cartera-dividendos',
    tag: 'Estrategia',
    date: '01 ago 2026',
    readTime: '9 min',
    title: 'Riesgo divisa en tu cartera de dividendos: por qué el euro/dólar decide parte de tu cobro',
    excerpt:
      'Si cobras dividendos de empresas USA o europeas fuera de la zona euro, el tipo de cambio mueve tu renta cada trimestre. Cuánto pesa, cómo se combina con la retención en origen y por qué cubrir la divisa casi nunca compensa en acciones.',
  },
  {
    slug: 'recompras-acciones-vs-dividendos',
    tag: 'Estrategia',
    date: '31 jul 2026',
    readTime: '9 min',
    title: 'Recompras de acciones vs dividendos: qué gana el accionista con cada una',
    excerpt:
      'Las recompras difieren el IRPF y suben tu parte del pastel; los dividendos son renta que llega sola. Cuándo un buyback crea valor, cómo detectar los que destruyen y por qué el shareholder yield mide mejor que el yield a secas.',
  },
  {
    slug: 'fiscalidad-opciones-irpf-espana',
    tag: 'Fiscalidad',
    date: '30 jul 2026',
    readTime: '10 min',
    title: 'Fiscalidad de las opciones en el IRPF: cómo tributan las primas de puts y calls',
    excerpt:
      'Las primas de opciones son ganancias patrimoniales sin retención, y se imputan al vencimiento, no al cobro. Qué pasa si te ejercitan, cómo tributa la covered call y dónde va todo en Renta Web.',
  },
  {
    slug: 'traspaso-acciones-entre-brokers',
    tag: 'Brokers',
    date: '29 jul 2026',
    readTime: '9 min',
    title: 'Traspasar acciones entre brokers: cómo cambiar de casa sin pagar peaje a Hacienda',
    excerpt:
      'El traspaso de valores no tributa; vender y recomprar sí. Cómo se solicita, cuánto cuesta por posición, por qué tus precios de compra pueden no viajar con los títulos y qué descargar antes de mudarte.',
  },
  {
    slug: 'formulario-w8ben-guia-espana',
    tag: 'Fiscalidad',
    date: '28 jul 2026',
    readTime: '8 min',
    title: 'Formulario W-8BEN en España: baja la retención de dividendos USA del 30% al 15%',
    excerpt: 'El W-8BEN es el papel que te ahorra la mitad de la retención de tus acciones y ETFs estadounidenses. Qué es, cómo rellenarlo en tu broker, que caduca a los 3 años y qué hacer si ya cobraste al 30%.',
  },
  {
    slug: 'que-pasa-si-quiebra-tu-broker',
    tag: 'Brokers',
    date: '26 jul 2026',
    readTime: '9 min',
    title: '¿Qué pasa con tus acciones si tu broker quiebra? FOGAIN y segregación',
    excerpt: 'Tus acciones no son del broker: están segregadas y no entran en la masa concursal. Cómo funcionan las cuentas ómnibus, qué cubre el FOGAIN (100.000 €) y por qué DEGIRO, Trade Republic e IBKR se rigen por esquemas de solo 20.000 €.',
  },
  {
    slug: 'regla-chowder-seleccion-dividendos',
    tag: 'Estrategia',
    date: '24 jul 2026',
    readTime: '8 min',
    title: 'La regla de Chowder: el filtro que separa un buen dividendo de una trampa',
    excerpt: 'El número de Chowder suma yield y crecimiento del dividendo en una sola cifra para filtrar acciones DGI. Cómo se calcula, los umbrales de 12 y 8, y por qué descarta trampas de yield alto que el yield solo no ve.',
  },
  {
    slug: 'heredar-acciones-irpf',
    tag: 'Fiscalidad',
    date: '24 jul 2026',
    readTime: '9 min',
    title: 'Heredar o donar acciones: la plusvalía del muerto y los errores que se pagan dos veces',
    excerpt: 'Heredar borra la ganancia acumulada en IRPF; donar la hace tributar dos veces. Coste de adquisición, pactos sucesorios, FIFO con lotes heredados y qué documentar el día de la herencia.',
  },
  {
    slug: 'dividendos-inflacion-poder-adquisitivo',
    tag: 'Estrategia',
    date: '23 jul 2026',
    readTime: '8 min',
    title: 'Dividendos e inflación: por qué tu poder adquisitivo importa más que el yield',
    excerpt: 'La inflación se come tu renta por dividendo aunque el yield suba. Cómo medir tu dividendo real, qué empresas aguantan la subida de precios y qué hacer para no perder poder adquisitivo.',
  },
  {
    slug: 'tipos-interes-cartera-dividendos',
    tag: 'Estrategia',
    date: '22 jul 2026',
    readTime: '11 min',
    title: 'Tipos de interés y tu cartera de dividendos: qué hacer cuando el BCE mueve el precio del dinero',
    excerpt: 'El BCE subió tipos en junio de 2026 y el mercado descuenta más subidas. Te explicamos por qué eso mueve tus bancos, utilities y SOCIMIs, y qué tocar en tu cartera de dividendos.',
  },
  {
    slug: 'dividend-aristocrats-europa-espana-2026',
    tag: 'Estrategia',
    date: '22 jul 2026',
    readTime: '11 min',
    title: 'Dividend Aristocrats en Europa y España: las acciones que suben el dividendo cada año',
    excerpt: 'Qué son los Dividend Aristocrats en Europa y España, qué empresas españolas entran en el índice S&P Europe 350 Dividend Aristocrats y cómo invertir en ellos desde España sin complicarte la fiscalidad.',
  },
  {
    slug: 'plan-ahorro-largo-plazo-pea',
    tag: 'Fiscalidad',
    date: '21 jul 2026',
    readTime: '9 min',
    title: 'Plan de Ahorro a Largo Plazo (PEA): dividendos al 0% de IRPF si aguantas 5 años',
    excerpt: 'Cómo funciona el PEA en España: exención del 0% en el IRPF para dividendos y plusvalías si mantienes el plan 5 años, el límite de 5.000€ al año y cómo declararlo en la Renta.',
  },
  {
    slug: 'rebalanceo-cartera-dividendos',
    tag: 'Estrategia',
    date: '16 jul 2026',
    readTime: '7 min',
    title: 'Rebalancear tu cartera de dividendos sin disparar a Hacienda',
    excerpt: 'Cómo corregir la deriva de tu cartera de dividendos con bandas de tolerancia y dinero nuevo, sin pagar más IRPF del necesario por vender.',
  },
  {
    slug: 'impuesto-patrimonio-inversores-espana',
    tag: 'Fiscal',
    date: '15 jul 2026',
    readTime: '12 min',
    title: 'Impuesto de Patrimonio 2026 para inversores: lo que pagas por tu cartera (y cómo minimizarlo)',
    excerpt: 'Guía práctica del Impuesto de Patrimonio para inversores en España: mínimo exento, valoración de acciones, fondos y ETFs, diferencias por Comunidad Autónoma, cómo declarar tu cartera en el Modelo 714 y estrategias legales para reducir lo que pagas.',
  },
  {
    slug: 'analisis-sectorial-dividendos-espana-2026',
    tag: 'Estrategia',
    date: '13 jul 2026',
    readTime: '12 min',
    title: 'Dónde invertir para dividendos en 2026: análisis sectorial completo',
    excerpt: 'La banca ya no es la reina del dividendo español. 26.399 M€ pagados en el primer semestre de 2026, pero el dinero está fluyendo hacia energía, utilities e infraestructuras. Análisis sectorial con datos reales y una propuesta práctica de asignación.',
  },
  {
    slug: 'mejores-etfs-dividendos-espana-2026',
    tag: 'Estrategia',
    date: '11 jul 2026',
    readTime: '13 min',
    title: 'Los mejores ETFs de dividendos para invertir desde España en 2026',
    excerpt: 'Guía práctica de los mejores ETFs de dividendos disponibles para inversores españoles: VHYL, FUSD, IQQY, SPDR Euro Dividend Aristocrats. TERs, yields, domicilios, fiscalidad y cómo elegir según tu perfil.',
  },
  {
    slug: 'dividendos-hacienda-foral-navarra-euskadi',
    tag: 'Fiscal',
    date: '10 jul 2026',
    readTime: '13 min',
    title: 'Dividendos en Navarra y País Vasco: qué cambia con Hacienda Foral',
    excerpt: 'Cómo tributan los dividendos en Navarra y el País Vasco. Diferencias con el régimen común, tipos aplicables y el impacto en tu cartera.',
  },
  {
    slug: 'opciones-ingresos-extra-dividendos',
    tag: 'Estrategia',
    date: '9 jul 2026',
    readTime: '12 min',
    title: 'Opciones para inversores de dividendos: ingresos extra con covered calls',
    excerpt: 'Cómo usar covered calls y cash-secured puts para generar ingresos adicionales sobre tu cartera de dividendos. Fiscalidad IRPF incluida.',
  },
  {
    slug: 'vivir-de-dividendos-20250707',
    tag: 'Estrategia',
    date: '7 jul 2026',
    readTime: '9 min',
    title: 'Vivir de los dividendos en España: el capital necesario y la realidad fiscal',
    excerpt: 'Cuánto capital necesitas para generar 2.000€ netos al mes y qué impacto tiene Hacienda en tu cartera. DGI, High Yield y CEFs comparados con números reales.',
  },
  {
    slug: 'metodo-dgi-construir-cartera-dividendos-20250705',
    tag: 'Estrategia',
    date: '5 jul 2025',
    readTime: '7 min',
    title: 'Cómo construir una cartera de dividendos desde cero: El método DGI',
    excerpt: 'Guía paso a paso para montar tu cartera de Dividend Growth Investing. Criterios de selección, métricas de seguridad y errores que te costarán dinero.',
  },
  {
    slug: 'seguridad-dividendo-metricas',
    tag: 'Métricas',
    date: '4 jul 2026',
    readTime: '13 min',
    title: 'Cómo analizar la seguridad del dividendo: las métricas que te alertan antes del recorte',
    excerpt: 'Aprende a evaluar si un dividendo es sostenible antes de que la empresa lo recorte. Payout ratio, free cash flow, cobertura y las señales de alerta que los inversores pasan por alto.',
  },
  {
    slug: 'total-return-vs-dividend-yield',
    tag: 'Métricas',
    date: '3 jul 2026',
    readTime: '11 min',
    title: 'Total return vs dividend yield: por qué el yield no es tu rentabilidad real',
    excerpt: 'El dividend yield es solo una parte de tu rentabilidad. Aprende a calcular el total return y por qué ignorar la revalorización te está costando dinero.',
  },
  {
    slug: 'broker-dividendos-espana-2025',
    tag: 'Estrategia',
    date: '1 jul 2026',
    readTime: '10 min',
    title: 'Mejor broker para cobrar dividendos en España (2025)',
    excerpt: 'Comparativa real de brokers para inversores en dividendos: TR, DEGIRO, IBKR e ING. Retenciones, informes fiscales y qué hacer con Hacienda.',
  },
  {
    slug: 'trampas-dividendo-yield-insostenible',
    tag: 'Estrategia',
    date: '1 jul 2026',
    readTime: '13 min',
    title: 'Trampas del dividendo: cómo detectar un yield insostenible antes de que sea tarde',
    excerpt: 'Una rentabilidad por dividendo del 12% suena demasiado bien porque suele serlo. Guía práctica para identificar dividendos insostenibles en el mercado español con ejemplos reales y métricas clave.',
  },
  {
    slug: 'planificacion-fiscal-fin-ano',
    tag: 'Fiscal',
    date: '29 jun 2026',
    readTime: '12 min',
    title: 'Planificación fiscal de fin de año para el inversor en dividendos: la guía que te ahorra dinero antes del 31 de diciembre',
    excerpt: 'Guía práctica para reducir tu factura fiscal antes del cierre del ejercicio: cuándo vender con pérdida, cómo manejar los tramos del ahorro, la regla de los 2 meses y un checklist de 7 pasos para diciembre.',
  },
  {
    slug: 'retencion-19-vs-tributacion-real-irpf',
    tag: 'Fiscal',
    date: '28 jun 2026',
    readTime: '11 min',
    title: 'La retención del 19% de los dividendos no es lo que pagas realmente',
    excerpt: 'Tu broker te retiene el 19% cuando cobras dividendos, pero ese no es tu impuesto real. Si tu base del ahorro supera los 6.000 €, acabas pagando hasta un 28%. Te explico la diferencia con ejemplos prácticos.',
  },
  {
    slug: 'dividendos-individuales-vs-etf-acumulacion-fiscal',
    tag: 'Estrategia',
    date: '27 jun 2026',
    readTime: '14 min',
    title: 'Acciones de dividendos vs ETFs de acumulación: la cuenta que nadie te hace',
    excerpt: 'Comparativa fiscal real entre una cartera DGI de acciones individuales y un ETF de acumulación en España. El tax drag a 20 años, cuánto pierdes por el camino y qué te conviene según tu perfil.',
  },
  {
    slug: 'derechos-suscripcion-preferente-irpf',
    tag: 'Fiscal',
    date: '26 jun 2026',
    readTime: '13 min',
    title: 'Derechos de suscripción preferente en el IRPF: qué hacer y cómo tributa cada opción',
    excerpt: 'Guía práctica sobre los derechos de suscripción preferente: las tres opciones (suscribir, vender en mercado, vender a la empresa), cómo tributa cada una en el IRPF, el cambio de 2017 y ejemplos con números reales.',
  },
  {
    slug: 'gastos-deducibles-inversion-irpf',
    tag: 'Fiscal',
    date: '25 jun 2026',
    readTime: '14 min',
    title: 'Gastos deducibles del inversor en el IRPF: qué comisiones y costes puedes restar',
    excerpt: 'Guía práctica sobre qué gastos de inversión son deducibles en el IRPF: comisiones de custodia, administración de valores, cánones de bolsa, gastos de divisa y cómo incluirlos en la declaración.',
  },
  {
    slug: 'criptomonedas-irpf-espana',
    tag: 'Fiscal',
    date: '23 jun 2026',
    readTime: '16 min',
    title: 'Criptomonedas en el IRPF: guía completa para declarar en España 2026',
    excerpt: 'Cómo tributan las criptomonedas en el IRPF: venta, permuta, staking, modelo 721, FIFO, casillas 1800-1814, DAC8 y ejemplos con números reales.',
  },
  {
    slug: 'reits-extranjeros-irpf-espana',
    tag: 'Fiscal',
    date: '24 jun 2026',
    readTime: '15 min',
    title: 'Dividendos de REITs extranjeros en el IRPF: guía fiscal para inversores desde España',
    excerpt: 'Cómo tributan los dividendos de REITs extranjeros (Realty Income, Prologis, Vonovia) en el IRPF: retenciones por país, convenios de doble imposición, casillas 029 y 0588, y ejemplos con números reales.',
  },
  {
    slug: 'prima-emision-reduccion-capital-irpf',
    tag: 'Fiscal',
    date: '22 jun 2026',
    readTime: '14 min',
    title: 'Prima de emisión y reducción de capital en el IRPF: qué tributa y qué no cuando la empresa devuelve tu dinero',
    excerpt: 'La prima de emisión y la reducción de capital no tributan como dividendo en la mayoría de casos. Guía práctica con ejemplos, la DGT V0215-26 de febrero 2026 y cómo afecta a tu cartera de dividendos.',
  },
  {
    slug: 'calendario-dividendos-irpf',
    tag: 'Estrategia',
    date: '20 jun 2026',
    readTime: '14 min',
    title: 'Calendario de dividendos: cómo planificar tus ingresos mes a mes',
    excerpt: 'Guía completa sobre el calendario de dividendos: fecha ex-dividendo, fecha de pago, cómo planificar ingresos mensuales con cartera mixta España-EE.UU. y errores frecuentes al cobrar.',
  },
  {
    slug: 'tramo-30-base-ahorro-irpf',
    tag: 'Fiscal',
    date: '18 jun 2026',
    readTime: '15 min',
    title: 'El nuevo tramo del 30% en la base del ahorro: cómo te afecta en la Renta 2026',
    excerpt: 'La Ley 7/2024 subió el último tramo del ahorro del 28% al 30% para rentas superiores a 300.000 €. Guía completa con ejemplos, estrategias de planificación y cómo minimizar el impacto en tu declaración.',
  },
  {
    slug: 'planes-pensiones-irpf',
    tag: 'Fiscal',
    date: '17 jun 2026',
    readTime: '18 min',
    title: 'Planes de pensiones en el IRPF: guía completa 2026 — límites, fiscalidad al rescate y ejemplos',
    excerpt: 'Todo sobre los planes de pensiones en el IRPF: límites de aportación (1.500 €, autónomos, planes de empleo, cónyuge), fiscalidad al rescate como rendimiento del trabajo, PPA vs plan vs fondo de inversión y errores que te cuestan dinero.',
  },
  {
    slug: 'socimi-dividendos-irpf-espana',
    tag: 'Fiscal',
    date: '16 jun 2026',
    readTime: '15 min',
    title: 'SOCIMIs en España: guía completa de fiscalidad en el IRPF para el inversor de dividendos',
    excerpt: 'Cómo tributan los dividendos de SOCIMIs en el IRPF: retención del 19%, gravamen especial del 19% para socios relevantes, régimen al 0% en Impuesto sobre Sociedades, comparativa fiscal con acciones y errores frecuentes al declarar.',
  },
  {
    slug: 'reinvertir-dividendos',
    tag: 'Estrategia',
    date: '15 jun 2026',
    readTime: '14 min',
    title: 'Reinvertir dividendos o cobrarlos en efectivo: qué es fiscalmente mejor en España',
    excerpt: 'Análisis con números reales sobre si conviene reinvertir dividendos (DRIP), usar fondos de acumulación o cobrar en efectivo. Fiscalidad IRPF, interés compuesto, ejemplos con 50.000€ y cuál elegir según tu situación.',
  },
  {
    slug: 'dividendos-extranjeros-doble-imposicion-irpf',
    tag: 'Fiscal',
    date: '15 jun 2026',
    readTime: '16 min',
    title: 'Dividendos extranjeros en el IRPF: cómo recuperar la doble imposición',
    excerpt: 'Guía práctica para declarar dividendos de acciones extranjeras en España: casilla 0029 y 0588, formulario W-8BEN, retenciones por país, exceso reclamable y ejemplos con IBKR, DeGiro y eToro.',
  },
  {
    slug: 'fondos-vs-etf-dividendos-espana',
    tag: 'Fiscal',
    date: '14 jun 2026',
    readTime: '15 min',
    title: 'Fondos de inversión vs ETFs de dividendos: la diferencia fiscal que te está costando dinero',
    excerpt: 'La diferencia fiscal entre fondos y ETFs de dividendos en España puede suponer miles de euros a lo largo de los años. Traspasos, tributación, ejemplos reales y cuál elegir según tu estrategia.',
  },
  {
    slug: 'scrip-dividend-irpf-espana',
    tag: 'Fiscal',
    date: '13 jul 2026',
    readTime: '14 min',
    title: 'Scrip dividend en España: qué es, cómo funciona y fiscalidad en el IRPF',
    excerpt: 'Guía completa sobre el scrip dividend o dividendo flexible: las 3 opciones del accionista (acciones nuevas, vender derechos o cobro en efectivo), tratamiento fiscal distinto para cada una, ejemplos con Telefónica y Repsol, y errores que te pueden costar dinero.',
  },
  {
    slug: 'modelo-720-bienes-extranjero',
    tag: 'Fiscal',
    date: '7 jul 2026',
    readTime: '16 min',
    title: 'Modelo 720: guía completa para declarar bienes en el extranjero',
    excerpt: 'Todo sobre el Modelo 720: quién está obligado, los tres bloques (cuentas, valores e inmuebles), umbrales de 50.000 €, plazos, sanciones tras la sentencia del TJUE y cómo declarar tus posiciones en brokers extranjeros como IBKR, DeGiro o eToro.',
  },
  {
    slug: 'plusvalias-espana-irpf-guia',
    tag: 'Fiscal',
    date: '18 jun 2026',
    readTime: '14 min',
    title: 'Cómo tributan las plusvalías en España: guía completa IRPF',
    excerpt: 'Guía definitiva sobre la fiscalidad de las plusvalías en España: tributación de ganancias patrimoniales por venta de acciones, compensación de pérdidas, regla de los dos meses, FIFO, plazos de arrastre y ejemplos prácticos para la Renta.',
  },
  {
    slug: 'dgi',
    tag: 'Estrategia',
    date: '26 may 2026',
    readTime: '8 min',
    title: 'La estrategia DGI: cómo invertir para vivir de dividendos',
    excerpt: 'Guía definitiva para invertir en dividendos crecientes: fundamentos, selección de acciones, fiscalidad, riesgos y alternativas para alcanzar la independencia financiera.',
  },
  {
    slug: 'declarar-dividendos-espana-guia-completa',
    tag: 'Fiscal',
    date: '7 jun 2026',
    readTime: '12 min',
    title: 'Cómo declarar los dividendos en España: guía completa',
    excerpt: 'Guía definitiva para declarar dividendos en España: casillas del Modelo 100, doble imposición internacional, retenciones por país, errores frecuentes, ejemplos prácticos y todo lo que necesitas para la Renta.',
  },
  {
    slug: 'yield-on-cost',
    tag: 'Métricas',
    date: '15 jun 2026',
    readTime: '12 min',
    title: 'Yield on cost: la métrica que los grandes inversores de dividendos miden',
    excerpt: 'Guía completa sobre el Yield on Cost (YOC): qué es, cómo se calcula, ejemplos reales con Coca-Cola, Realty Income, Apple y Johnson & Johnson, comparativa con otras métricas, errores fiscales en España y cómo usarlo para evaluar tu cartera de dividendos.',
  },
  {
    slug: 'compensar-perdidas-ganancias-irpf',
    tag: 'Fiscal',
    date: '17 jul 2026',
    readTime: '16 min',
    title: 'Compensar pérdidas con ganancias en el IRPF: guía completa',
    excerpt:
      'Guía práctica para compensar pérdidas con ganancias en la base del ahorro del IRPF: regla del 25%, compensación cruzada entre bloques, regla de los 2 meses, arrastre de 4 años y ejemplos numéricos paso a paso.',
  },
] as const satisfies readonly PostMeta[];

export type PostSlug = (typeof POST_META)[number]['slug'];

/** One index entry, with `slug` narrowed to the literal union so `POST_IMAGES` can be indexed by it. */
export type Post = (typeof POST_META)[number];

const MONTHS: Record<string, number | undefined> = {
  ene: 1, feb: 2, mar: 3, abr: 4, may: 5, jun: 6,
  jul: 7, ago: 8, sep: 9, oct: 10, nov: 11, dic: 12,
};

/** `'21 ago 2026'` → a sortable number. Throws rather than silently sorting to the end. */
export function postDateKey(date: string): number {
  const m = /^(\d{1,2}) (\w+) (\d{4})$/.exec(date);
  const month = m ? MONTHS[m[2]] : undefined;
  if (!m || month === undefined) {
    throw new Error(`Blog post date is not 'D mmm YYYY': ${date}`);
  }
  return Number(m[3]) * 10000 + month * 100 + Number(m[1]);
}

/**
 * Slugs that actually have an article. A directory only counts once it holds a
 * `page.mdx` — the same rule `sitemap.ts` applies, so the index and the sitemap
 * cannot disagree about what exists.
 */
export function postSlugsOnDisk(blogDir = path.join(process.cwd(), 'src', 'app', 'blog')): string[] {
  return fs
    .readdirSync(blogDir, { withFileTypes: true })
    .filter((e) => e.isDirectory() && fs.existsSync(path.join(blogDir, e.name, 'page.mdx')))
    .map((e) => e.name)
    .sort();
}

/** Throws when the index and the filesystem disagree, naming both directions. */
export function assertIndexMatchesDisk(onDisk: readonly string[]): void {
  const indexed = new Set<string>(POST_META.map((p) => p.slug));
  const orphans = onDisk.filter((s) => !indexed.has(s));
  const dangling = POST_META.map((p) => p.slug).filter((s) => !onDisk.includes(s));
  if (!orphans.length && !dangling.length) return;

  const parts = ['Blog index is out of sync with app/blog/.'];
  if (orphans.length) {
    parts.push(`Articles with no card (unreachable from /blog): ${orphans.join(', ')}`);
  }
  if (dangling.length) {
    parts.push(`Cards with no article (they link to a 404): ${dangling.join(', ')}`);
  }
  throw new Error(parts.join('\n  '));
}

/**
 * The index, newest first. Runs at build time — the blog routes are statically
 * prerendered — so a drifted index fails the build rather than shipping a dead
 * card, and costs nothing per request.
 */
export function blogPosts(): readonly Post[] {
  assertIndexMatchesDisk(postSlugsOnDisk());
  return [...POST_META].sort((a, b) => postDateKey(b.date) - postDateKey(a.date));
}
