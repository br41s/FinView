/**
 * Single source of the legal facts the public documents under /legal state.
 *
 * The four pages (aviso legal, privacidad, cookies, condiciones) interpolate
 * these values instead of repeating them, so a change of owner, address or
 * sub-processor is one edit here and cannot leave one document behind.
 *
 * The identity is the one Biglobster LLC publishes on biglobster.top; keep the
 * two in step if the company's registered details change.
 */
export const LEGAL = {
  brand: "FinView",
  owner: "Biglobster LLC",
  /**
   * The owner's site. It is the legal reference for every Biglobster LLC app
   * and page: FinView's documents follow the approach published there. Linked
   * from the footer and the legal pages so a reader can check who is behind
   * the product (and so the group's sites reference each other).
   */
  ownerUrl: "https://biglobster.top",
  ownerBrand: "BigLobster",
  ownerTagline: "IA práctica para autónomos, profesionales y pymes",
  legalForm:
    "sociedad de responsabilidad limitada (LLC) constituida en el estado de Nuevo México (Estados Unidos)",
  registration: "3279115 (Entity ID 0008120949, Secretaría de Estado de Nuevo México)",
  address: "1209 Mountain Road Pl NE Ste N, Albuquerque, NM 87110, Estados Unidos",
  /** Must be a mailbox somebody reads: rights requests have a one-month deadline. */
  email: "hola@biglobster.top",
} as const;

/**
 * Date shown as "Última actualización" on every legal page. It is also the
 * value of `TERMS_VERSION` in backend/services/auth_service.py, which is what
 * a user's acceptance is recorded against: bump both together when a document
 * changes in a way users must re-accept.
 */
export const LEGAL_UPDATED = "15 de octubre de 2026";

/**
 * The product's position on advice, in one place so every surface says the same
 * thing: FinView shows data, the user decides. Rendered by AiDisclaimer, the
 * public footer, the sign-up form and the terms banner; /legal/condiciones §3
 * is the long form.
 */
export const NOT_ADVICE = {
  /** One line, for footers and tight spaces. */
  short:
    "FinView muestra datos, no consejos. No es asesoramiento financiero: invertir o no es decisión tuya.",
  /** Next to machine-generated signals and text. */
  signals:
    "FinView muestra datos, no consejos. Las señales y los textos se generan automáticamente, en parte con IA: no son asesoramiento financiero ni una recomendación de compra o venta, y no tienen en cuenta tu situación. La decisión de invertir o no es solo tuya.",
  /** Wherever a hit rate or backtest is shown. */
  pastPerformance: "Los aciertos pasados no garantizan resultados futuros.",
} as const;

export interface Processor {
  name: string;
  purpose: string;
  data: string;
  location: string;
  safeguard: string;
}

/** Recipients of personal data (GDPR art. 13.1.e-f and art. 28). */
export const PROCESSORS: Processor[] = [
  {
    name: "Biglobster LLC (personal autorizado)",
    purpose: "Operación del servicio, mantenimiento y soporte. Acceso a los sistemas desde Tailandia",
    data: "Los datos de la cuenta que sea necesario consultar para mantener el servicio o atender una solicitud",
    location: "Tailandia",
    safeguard:
      "Cláusulas contractuales tipo (art. 46.2.c RGPD). Tailandia no cuenta con decisión de adecuación",
  },
  {
    name: "Google Cloud EMEA Limited (Cloud Run)",
    purpose: "Alojamiento del servidor de la aplicación",
    data: "Todos los datos de la cuenta, en tránsito y durante el cálculo",
    location: "Bélgica (UE), región europe-west1",
    safeguard: "Tratamiento dentro del EEE",
  },
  {
    name: "Neon, Inc.",
    purpose: "Base de datos",
    data: "Todos los datos de la cuenta",
    location: "Alemania (UE), región eu-central-1",
    safeguard: "Datos alojados en el EEE; cláusulas contractuales tipo para accesos de soporte",
  },
  {
    name: "Vercel Inc.",
    purpose: "Alojamiento de la web y enrutado de peticiones",
    data: "Dirección IP, cookie de sesión y datos en tránsito",
    location: "UE y Estados Unidos",
    safeguard: "Marco de Privacidad de Datos UE-EE. UU. y cláusulas contractuales tipo",
  },
  {
    name: "Cloudflare, Inc. (Turnstile)",
    purpose: "Verificación anti-robots al iniciar sesión",
    data: "Dirección IP y señales técnicas del navegador",
    location: "UE y Estados Unidos",
    safeguard: "Marco de Privacidad de Datos UE-EE. UU. y cláusulas contractuales tipo",
  },
  {
    name: "OpenRouter, Inc. y el proveedor del modelo de IA",
    purpose: "Generación de los análisis automáticos de opciones y zonas clave",
    data: "Tickers que sigues, datos de mercado y el texto que escribes al asistente. Nunca tu nombre, email ni importes de tu cartera",
    location: "Estados Unidos y otros países fuera del EEE",
    safeguard: "Envío sin identificadores personales; cláusulas contractuales tipo",
  },
];
