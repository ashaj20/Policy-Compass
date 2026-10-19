"""Security headers on every response, including who may show our pages in a frame.

Only public pages (/p/...) may be framed, so organisations can embed them in their websites
(US-030). Everything else, the internal app and the API, refuses to be framed, which protects
signed-in staff from clickjacking (US-037).
"""

from starlette.types import ASGIApp, Message, Receive, Scope, Send

EMBEDDABLE_PREFIX = "/p/"


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        embeddable = scope.get("path", "").startswith(EMBEDDABLE_PREFIX)

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = [
                    (k, v)
                    for k, v in message.get("headers", [])
                    if k.lower() not in (b"x-frame-options",)
                ]
                names = {k.lower() for k, _ in headers}
                ancestors = b"frame-ancestors *" if embeddable else b"frame-ancestors 'none'"
                csp = next((v for k, v in headers if k.lower() == b"content-security-policy"), None)
                if csp is None:
                    headers.append((b"content-security-policy", ancestors))
                elif b"frame-ancestors" not in csp:
                    headers = [
                        (k, v + b"; " + ancestors if k.lower() == b"content-security-policy" else v)
                        for k, v in headers
                    ]
                if not embeddable:
                    headers.append((b"x-frame-options", b"DENY"))
                if b"x-content-type-options" not in names:
                    headers.append((b"x-content-type-options", b"nosniff"))
                if b"referrer-policy" not in names:
                    headers.append((b"referrer-policy", b"strict-origin-when-cross-origin"))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)
