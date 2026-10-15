"""IBKR Flex Web Service client (v3): SendRequest → reference code → GetStatement.

The token travels in the query string because that is IBKR's API. It must never
reach a log line or an exception message, so nothing here logs a URL or lets an
httpx exception (whose text includes the URL) escape: every failure is re-raised
as a `FlexError` with a Spanish message the API can show as is.

Error codes are IBKR's v3 table (ibkrguides.com/clientportal/flex3.htm). They
fall into three kinds, and the sync service acts on the kind, not the number:
  - transient: the statement is not ready or IBKR is busy; ask again later.
  - connection: the token or query is unusable; nothing will work until the
    user fixes it in IBKR's Client Portal.
  - anything else: this one statement failed; other years may still work.
"""

import logging
import re
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

import httpx

from backend.config import settings

logger = logging.getLogger(__name__)

_TOKEN_PARAM = re.compile(r"([?&]t=)[^&\s\"]+")


class _RedactFlexToken(logging.Filter):
    """httpx logs every request URL at INFO, and a Flex URL carries the token."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        if "FlexWebService" in message:
            record.msg = _TOKEN_PARAM.sub(r"\1***", message)
            record.args = ()
        return True


logging.getLogger("httpx").addFilter(_RedactFlexToken())

USER_AGENT = "FinView/1.0 (+https://finview.app)"
HTTP_TIMEOUT = 20.0
# IBKR's ceiling per token; above it every call answers 1018 until the minute passes.
REQUESTS_PER_MINUTE = 10

# The statement is not ready, or IBKR is momentarily unable to serve it.
TRANSIENT_CODES = frozenset(
    {"1001", "1004", "1005", "1006", "1007", "1008", "1009", "1018", "1019", "1021"}
)
# The token, query or account is unusable until the user acts in IBKR.
# Not an IBKR code: the statement arrived in a format other than XML.
FORMAT_CODE = "format"
CONNECTION_CODES = frozenset(
    {"1010", "1011", "1012", "1013", "1014", "1015", "1016", FORMAT_CODE}
)
# The reference code we hold is no longer valid: request the statement again.
STALE_REFERENCE_CODES = frozenset({"1017"})

_MESSAGES = {
    "1010": "La Flex Query es de tipo antiguo. Crea una Activity Flex Query nueva en IBKR.",
    "1011": "IBKR indica que el servicio Flex de la cuenta no está activo.",
    "1012": "El token de IBKR ha caducado. Genera uno nuevo en el Portal de Clientes "
    "y vuelve a conectar.",
    "1013": "El token de IBKR está restringido a otra dirección IP. "
    "Genera un token sin restricción de IP.",
    "1014": "IBKR no reconoce el ID de la Flex Query. Revisa el número que copiaste.",
    "1015": "IBKR no reconoce el token. Revisa que lo hayas copiado entero.",
    "1016": "IBKR indica que la cuenta no es válida para este token.",
    "1018": "IBKR limita las peticiones por minuto; se reintentará en unos segundos.",
    "1019": "IBKR está generando el informe.",
}


class FlexError(Exception):
    """A failure the caller can show to the user (message is Spanish, token-free)."""

    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.code = code

    @property
    def transient(self) -> bool:
        return self.code in TRANSIENT_CODES

    @property
    def connection(self) -> bool:
        return self.code in CONNECTION_CODES

    @property
    def stale_reference(self) -> bool:
        return self.code in STALE_REFERENCE_CODES


class _Paced(httpx.BaseTransport):
    """At most REQUESTS_PER_MINUTE requests in any 60 s through this transport.

    One instance per token. It waits instead of letting IBKR answer 1018: the sync
    treats 1018 as transient and asks again, which keeps the token over the limit.
    """

    def __init__(
        self,
        inner: httpx.BaseTransport,
        *,
        sleep: Callable[[float], None],
        clock: Callable[[], float],
    ):
        self._inner = inner
        self._sleep = sleep
        self._clock = clock
        self._sent: list[float] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        now = self._clock()
        self._sent = [t for t in self._sent if now - t < 60.0]
        if len(self._sent) >= REQUESTS_PER_MINUTE:
            self._sleep(60.0 - (now - self._sent[0]))
        self._sent.append(self._clock())
        return self._inner.handle_request(request)

    def close(self) -> None:
        self._inner.close()


def paced_client(
    transport: httpx.BaseTransport | None = None,
    *,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> httpx.Client:
    """A client for one token that never exceeds IBKR's per-minute limit."""
    return httpx.Client(
        transport=_Paced(transport or httpx.HTTPTransport(), sleep=sleep, clock=clock),
        timeout=HTTP_TIMEOUT,
        headers={"User-Agent": USER_AGENT},
    )


def _error_from_code(code: str) -> FlexError:
    message = _MESSAGES.get(code)
    if message is None:
        message = (
            "IBKR está ocupado; se reintentará en unos segundos."
            if code in TRANSIENT_CODES
            else f"IBKR no pudo generar el informe (código {code})."
        )
    return FlexError(message, code)


def _get(path: str, params: dict[str, str], client: httpx.Client | None) -> str:
    url = f"{settings.ibkr_flex_url}/{path}"
    try:
        if client is not None:
            response = client.get(url, params=params)
        else:
            with httpx.Client(timeout=HTTP_TIMEOUT, headers={"User-Agent": USER_AGENT}) as c:
                response = c.get(url, params=params)
    except httpx.HTTPError as exc:
        # str(exc) can carry the URL, and the URL carries the token.
        logger.warning("IBKR Flex %s failed: %s", path, type(exc).__name__)
        raise FlexError("No se pudo contactar con IBKR. Inténtalo de nuevo en unos minutos.") from None
    if response.status_code != 200:
        logger.warning("IBKR Flex %s answered HTTP %s", path, response.status_code)
        raise FlexError(f"IBKR respondió con un error HTTP {response.status_code}.")
    return response.text


def _status_response(text: str) -> ET.Element | None:
    """The FlexStatementResponse envelope, or None when the body is a statement."""
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        raise FlexError("IBKR devolvió una respuesta que no es XML.") from None
    return root if root.tag == "FlexStatementResponse" else None


def _raise_on_failure(envelope: ET.Element, path: str) -> None:
    status = (envelope.findtext("Status") or "").strip()
    if status == "Success":
        return
    code = (envelope.findtext("ErrorCode") or "").strip()
    logger.info(
        "IBKR Flex %s status=%s code=%s message=%s",
        path,
        status,
        code,
        (envelope.findtext("ErrorMessage") or "").strip(),
    )
    if not code:
        raise FlexError("IBKR devolvió una respuesta sin código de error reconocible.")
    raise _error_from_code(code)


def send_request(
    token: str,
    query_id: str,
    from_date: date,
    to_date: date,
    *,
    client: httpx.Client | None = None,
) -> str:
    """Ask IBKR to generate the statement for [from_date, to_date]; return its reference."""
    text = _get(
        "SendRequest",
        {
            "t": token,
            "q": query_id,
            "v": "3",
            "fd": from_date.strftime("%Y%m%d"),
            "td": to_date.strftime("%Y%m%d"),
        },
        client,
    )
    envelope = _status_response(text)
    if envelope is None:
        raise FlexError("IBKR devolvió una respuesta inesperada al pedir el informe.")
    _raise_on_failure(envelope, "SendRequest")
    reference = (envelope.findtext("ReferenceCode") or "").strip()
    if not reference:
        raise FlexError("IBKR no devolvió un código de referencia para el informe.")
    return reference


def get_statement(token: str, reference: str, *, client: httpx.Client | None = None) -> str:
    """Return the statement XML, or raise FlexError (transient while it is generating)."""
    text = _get("GetStatement", {"t": token, "q": reference, "v": "3"}, client)
    try:
        envelope = _status_response(text)
    except FlexError:
        # The statement itself, in another format (CSV or text): every year
        # would fail the same way, so it is the query's problem, not this year's.
        raise FlexError(
            "IBKR entrega el informe en un formato que no es XML. "
            "Configura la Flex Query con formato XML.",
            FORMAT_CODE,
        ) from None
    if envelope is not None:
        _raise_on_failure(envelope, "GetStatement")
        # A Success envelope instead of a statement is not something to import.
        raise FlexError("IBKR devolvió una respuesta inesperada al descargar el informe.")
    return text


@dataclass
class PollResult:
    xml: str | None  # None: still generating when the budget ran out


def poll_statement(
    token: str,
    reference: str,
    *,
    budget_seconds: float,
    interval_seconds: float = 5.0,
    client: httpx.Client | None = None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> PollResult:
    """Fetch the statement, retrying transient answers until the budget is spent.

    Bounded because production work must finish inside the HTTP request: when
    the budget runs out the caller keeps the reference and asks again next call.
    Interval ≥ 5 s keeps a step well under IBKR's 10 requests per minute.
    """
    deadline = clock() + budget_seconds
    while True:
        try:
            return PollResult(get_statement(token, reference, client=client))
        except FlexError as exc:
            if not exc.transient or clock() + interval_seconds > deadline:
                if exc.transient:
                    return PollResult(None)
                raise
        sleep(interval_seconds)
