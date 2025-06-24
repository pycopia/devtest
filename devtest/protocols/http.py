"""A REST/HTTP for both synchronous and asynchronous clients.
"""

import socket
import ssl
import hashlib
from typing import Any, Callable, Tuple, Optional, Iterable, Union, cast
from typing.io import BinaryIO
from http import cookies

import h11
import rfc3986
from rfc3986 import builder

from devtest import json
from devtest.core import exceptions
from devtest.io import ssl as async_ssl
from devtest.io import socket as async_socket

__all__ = ['HttpControllerError', 'AsyncWebInterface', 'SyncWebInterface', 'HttpProtocolError',
           'SimpleWebInterface']


TargetEncoder = Callable[[str, Optional[dict]], str]


class HttpControllerError(exceptions.ControllerError):
    """Raised for any error in the HTTP interface."""


class HttpProtocolError(Exception):
    """Raised for any error in the HTTP interface."""

    @property
    def code(self):
        return self.args[0]

    @property
    def reason(self):
        return self.args[1]

    @property
    def body(self) -> Union[bytes, None]:
        """Body of response indicating an error, if known."""
        try:
            return self._body
        except AttributeError:
            return None

    @body.setter
    def body(self, body: bytes):
        self._body = body


class HttpResponseError(HttpProtocolError):
    """Raised for any error in the HTTP interface."""


class HttpProtocolRedirect(HttpProtocolError):
    """Raised when redirect is requested."""



def _default_target_encoder(path: str, params: Optional[dict] = None):
    url = builder.URIBuilder()
    url = url.add_path(path)
    if params:
        url = url.add_query_from(params)
    return url.finalize().unsplit()


class _WebInterface:

    def __init__(self,
                 hostname: str,
                 target_encoder: TargetEncoder = _default_target_encoder,
                 accept: str = "application/json",
                 extra_headers: Optional[list] = None,
                 port: int = 80,
                 usessl: bool = False):
        self._hostname = hostname
        self._port = port
        self._usessl = usessl
        self.protocol = "https" if usessl else "http"
        self._sock: Optional[async_socket.Socket] = None
        self._conn: Optional[h11.Connection] = None
        self._target_encoder: TargetEncoder = target_encoder
        self._ssl_context = None
        self._headers = [
            ("Host", self._hostname),
            ("User-Agent", h11.PRODUCT_ID),
            ("Accept", accept),
            ("Connection", "close"),
        ]
        if extra_headers and isinstance(extra_headers, list):
            self._headers.extend(extra_headers)

    def fileno(self):
        if self._sock is not None:
            return self._sock.fileno()
        else:
            return -1

    def get_headers(self, *tuples):
        """get base HTTP headers with additions appended."""
        return self._headers + list(tuples)

    @classmethod
    def from_url(cls,
                 urlstr,
                 target_encoder=_default_target_encoder,
                 accept="text/*",
                 extra_headers=None):
        url = rfc3986.urlparse(urlstr)
        cl = cls(hostname=url.host,
                 target_encoder=target_encoder,
                 accept=accept,
                 extra_headers=extra_headers,
                 port=url.port or 80)
        cl.protocol = url.scheme
        return cl


class AsyncWebInterface(_WebInterface):
    """Asynchronous, non-blocking HTTP interface."""

    async def close(self):
        if self._sock is not None:
            await self._send_event(h11.ConnectionClosed())
            await self._sock.close()
            self._sock = None
            self._conn = None
            self._ssl_context = None

    async def _send_event(self, event):
        assert self._conn is not None
        msg = self._conn.send(event)
        if msg:
            await self._sock.sendall(msg)

    async def _next_event(self):
        while True:
            event = self._conn.next_event()
            if event is h11.NEED_DATA:
                data = await self._sock.recv(65536)
                self._conn.receive_data(data)
                continue
            return event

    async def _connect(self):
        if self._sock is None:
            self._conn = h11.Connection(our_role=h11.CLIENT)
            sock = await async_socket.create_connection((self._hostname, self._port))
            if self.protocol.endswith("s"):
                ctx = async_ssl.create_default_context()
                sock = await ctx.wrap_socket(sock, server_hostname=self._hostname)
                self._ssl_context = ctx
            self._sock = sock

    async def get_request(self, path, filestream=None, params=None):
        await self._connect()
        body = []
        headers = []
        hasher = hashlib.sha256()
        content_type = None
        req_event = h11.Request(method="GET",
                                target=self._target_encoder(path, params),
                                headers=self._headers)
        msg = self._conn.send(req_event)
        await self._sock.sendall(msg)
        await self._send_event(h11.EndOfMessage())
        while True:
            ev = await self._next_event()
            evt = type(ev)
            if evt is h11.EndOfMessage:
                await self.close()
                break
            elif evt is h11.ConnectionClosed:
                await self.close()
                break
            elif evt is h11.Response:
                if ev.status_code not in (200, 201, 304):
                    raise HttpControllerError(
                        f"Bad HTTP response, code: {ev.status_code} {ev.reason}")
                headers = list(ev.headers)
                for header_name, header_value in ev.headers:
                    if header_name == b"content-type":
                        content_type = header_value
            elif evt is h11.Data:
                if filestream is not None:
                    filestream.write(ev.data)
                    hasher.update(ev.data)
                else:
                    body.append(ev.data)
        if filestream is None:
            return headers, _decode_content(content_type, b"".join(body))
        else:
            return headers, hasher.hexdigest()

    async def head_request(self, path, params=None):
        await self._connect()
        headers = []
        req_event = h11.Request(method="HEAD",
                                target=self._target_encoder(path, params),
                                headers=self._headers)
        msg = self._conn.send(req_event)
        await self._sock.sendall(msg)
        await self._send_event(h11.EndOfMessage())
        while True:
            ev = await self._next_event()
            evt = type(ev)
            if evt is h11.EndOfMessage:
                await self.close()
                break
            elif evt is h11.ConnectionClosed:
                await self.close()
                break
            elif evt is h11.Response:
                if ev.status_code not in (200, 201, 304):
                    raise HttpControllerError(
                        f"Bad HTTP response, code: {ev.status_code} {ev.reason}")
                headers = list(ev.headers)
        return headers

    async def _request_with_data(self, method, path, data=None, params=None):
        await self._connect()
        content_type = None
        if data:
            body = json.encode_bytes(data)
            headers = self.get_headers((b"Content-Type", b"application/json; charset=UTF-8"),
                                       (b"Content-Length", str(len(body)).encode("ascii")))
        else:
            body = None
            headers = self.get_headers()
        req_event = h11.Request(
            method=method,
            target=self._target_encoder(path, params),
            headers=headers,
        )
        msg = self._conn.send(req_event)
        await self._sock.sendall(msg)
        if body:
            msg = self._conn.send(h11.Data(data=body))
            await self._sock.sendall(msg)
        await self._send_event(h11.EndOfMessage())

        resp_body = []
        while True:
            ev = await self._next_event()
            evt = type(ev)
            if evt is h11.EndOfMessage:
                await self.close()
                break
            elif evt is h11.ConnectionClosed:
                await self.close()
                break
            elif evt is h11.Response:
                if ev.status_code not in (200, 201):
                    raise HttpControllerError(
                        f"Bad HTTP response, code: {ev.status_code} {ev.reason}")
                for header_name, header_value in ev.headers:
                    if header_name == b"content-type":
                        content_type = header_value
            elif evt is h11.Data:
                resp_body.append(ev.data)
        if resp_body:
            return _decode_content(content_type, b"".join(resp_body))

    async def put_request(self, path, data=None, params=None):
        return await self._request_with_data("PUT", path, data=data, params=params)

    async def post_request(self, path, data=None, params=None):
        return await self._request_with_data("POST", path, data=data, params=params)

    async def delete_request(self, path, params=None):
        await self._connect()
        req_event = h11.Request(method="DELETE",
                                target=self._target_encoder(path, params),
                                headers=self._headers)
        msg = self._conn.send(req_event)
        await self._sock.sendall(msg)
        await self._send_event(h11.EndOfMessage())
        while True:
            ev = await self._next_event()
            evt = type(ev)
            if evt is h11.EndOfMessage:
                self.close()
                break
            elif evt is h11.ConnectionClosed:
                self.close()
                break
            elif evt is h11.Response:
                if ev.status_code not in (200, 204):
                    raise HttpControllerError(
                        f"Bad HTTP response, code: {ev.status_code} {ev.reason}")


class SyncWebInterface(_WebInterface):
    """Blocking HTTP interface."""

    def __del__(self):
        self.close()

    def close(self):
        if self._sock is not None:
            self._send_event(h11.ConnectionClosed())
            self._sock.close()
            self._sock = None
            self._conn = None

    def _send_event(self, event):
        msg = self._conn.send(event)
        if msg:
            self._sock.sendall(msg)

    def _next_event(self):
        while True:
            event = self._conn.next_event()
            if event is h11.NEED_DATA:
                data = self._sock.recv(65536)
                self._conn.receive_data(data)
                continue
            return event

    def _connect(self):
        if self._sock is None:
            self._conn = h11.Connection(our_role=h11.CLIENT)
            sock = socket.create_connection((self._hostname, self._port))
            # TODO(dart) ssl
            self._sock = sock

    def get_request(self, path, filestream=None, params=None):
        """Perform a GET with optional query parameters."""
        self._connect()
        body = []
        headers = []
        hasher = hashlib.sha256()
        content_type = None
        req_event = h11.Request(method="GET",
                                target=self._target_encoder(path, params),
                                headers=self._headers)
        msg = self._conn.send(req_event)
        self._sock.sendall(msg)
        self._send_event(h11.EndOfMessage())
        while True:
            ev = self._next_event()
            evt = type(ev)
            if evt is h11.EndOfMessage:
                self.close()
                break
            elif evt is h11.ConnectionClosed:
                self.close()
                break
            elif evt is h11.Response:
                if ev.status_code not in (200, 201, 304):
                    raise HttpControllerError(
                        f"Bad HTTP response, code: {ev.status_code} {ev.reason}")
                headers = ev.headers[:]
                for header_name, header_value in ev.headers:
                    if header_name == b"content-type":
                        content_type = header_value
            elif evt is h11.Data:
                if filestream is not None:
                    filestream.write(ev.data)
                    hasher.update(ev.data)
                else:
                    body.append(ev.data)
        if filestream is None:
            return headers, _decode_content(content_type, b"".join(body))
        else:
            return headers, hasher.hexdigest()

    def _request_with_data(self, method, path, data=None, params=None):
        self._connect()
        content_type = None
        if data:
            body = json.encode_bytes(data)
            headers = self.get_headers((b"Content-Type", b"application/json; charset=UTF-8"),
                                       (b"Content-Length", str(len(body)).encode("ascii")))
        else:
            body = None
            headers = self.get_headers()
        req_event = h11.Request(
            method=method,
            target=self._target_encoder(path, params),
            headers=headers,
        )
        msg = self._conn.send(req_event)
        self._sock.sendall(msg)
        if body:
            msg = self._conn.send(h11.Data(data=body))
            self._sock.sendall(msg)
        self._send_event(h11.EndOfMessage())

        resp_body = []
        while True:
            ev = self._next_event()
            evt = type(ev)
            if evt is h11.EndOfMessage:
                self.close()
                break
            elif evt is h11.ConnectionClosed:
                self.close()
                break
            elif evt is h11.Response:
                if ev.status_code not in (200, 201):
                    raise HttpControllerError(
                        f"Bad HTTP response, code: {ev.status_code} {ev.reason}")
                for header_name, header_value in ev.headers:
                    if header_name == b"content-type":
                        content_type = header_value
            elif evt is h11.Data:
                resp_body.append(ev.data)
        if resp_body:
            return _decode_content(content_type, b"".join(resp_body))

    def put_request(self, path, data=None, params=None):
        return self._request_with_data("PUT", path, data=data, params=params)

    def post_request(self, path, data=None, params=None):
        return self._request_with_data("POST", path, data=data, params=params)

    def delete_request(self, path, params=None):
        self._connect()
        req_event = h11.Request(method="DELETE",
                                target=self._target_encoder(path, params),
                                headers=self._headers)
        msg = self._conn.send(req_event)
        self._sock.sendall(msg)
        self._send_event(h11.EndOfMessage())
        while True:
            ev = self._next_event()
            evt = type(ev)
            if evt is h11.EndOfMessage:
                self.close()
                break
            elif evt is h11.ConnectionClosed:
                self.close()
                break
            elif evt is h11.Response:
                if ev.status_code not in (200, 204):
                    raise HttpControllerError(
                        f"Bad HTTP response, code: {ev.status_code} {ev.reason}")


def _decode_content(content_type, data):
    if content_type and b"json" in content_type:
        return json.decode_bytes(data)
    else:
        raise HttpControllerError(f"Unhandled content-type: {content_type}.")


class SimpleWebInterface:
    """Simple, blocking HTTP/HTTPS client interface."""

    def __init__(self, baseurl: str, extra_headers: Optional[Iterable[Tuple]] = None):
        self._url = url = builder.URIBuilder.from_uri(baseurl)
        if not url.port:
            url.port = "443" if url.scheme == "https" else "80"
        self._headers = [
            ("Host", self._url.host),
            ("User-Agent", h11.PRODUCT_ID),
            ("Connection", "keep-alive"),
        ]
        if extra_headers and isinstance(extra_headers, list):
            self._headers.extend(extra_headers)
        self._need_ssl: bool = url.scheme.endswith("s")
        self._sock: Optional[socket.SocketType] = None
        self._conn: Optional[h11.Connection] = None
        self._cookie: cookies.SimpleCookie = cookies.SimpleCookie()

    def __del__(self):
        self.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()

    def fileno(self) -> int:
        if self._sock is not None:
            return self._sock.fileno()
        else:
            return -1

    @property
    def baseurl(self):
        return self._url.finalize().unsplit()

    def get_headers(self, *tuples):
        """get base HTTP headers with additions appended."""
        hl = self._headers + list(tuples)
        cookieval = self._cookie.output(attrs={}, header="", sep="; ").strip()
        if cookieval:
            hl.append(("Cookie", cookieval))
        return hl

    def close(self):
        if self._sock is not None:
            self._send_event(h11.ConnectionClosed())
            self._sock.close()
            self._sock = None
            self._conn = None

    def _send_event(self, event):
        msg = self._conn.send(event)
        if msg:
            self._sock.sendall(msg)

    def _next_event(self):
        while True:
            event = self._conn.next_event()
            if event is h11.NEED_DATA:
                data = self._sock.recv(65536)
                if not data:  # Try once more if no data, may be keep-alive connection.
                    data = self._sock.recv(65536)
                self._conn.receive_data(data)
                continue
            return event

    def _connect(self):
        if self._sock is None:
            self._sock = socket.create_connection((self._url.host, int(self._url.port)))
            if self._need_ssl:
                context = ssl.create_default_context()
                self._sock = context.wrap_socket(self._sock, server_hostname=self._url.host)
            self._conn = h11.Connection(our_role=h11.CLIENT)

    def _request(self,
                 method: str,
                 path: str,
                 data: Optional[Any] = None,
                 content_type: Optional[str] = None,
                 fragment: Optional[str] = None,
                 query: Optional[str] = None,
                 params: Optional[dict] = None) -> Tuple[list, Any]:
        self._connect()
        resp_headers = []
        msgbody = None
        send_headers = self.get_headers()
        if content_type:
            cast(str, content_type)
            send_headers.append((b"Content-Type", content_type.encode("ascii")))
            if data:
                msgbody = self.encode_content(content_type, data)
                send_headers.append((b"Content-Length", str(len(msgbody)).encode("ascii")))
        target = self.encode_target(path=path, fragment=fragment, query=query, params=params)
        req_event = h11.Request(method=method, target=target, headers=send_headers)
        # asserts are for mypy type checking
        assert self._conn is not None
        assert self._sock is not None
        msg = self._conn.send(req_event)
        assert msg is not None
        self._sock.sendall(msg)
        if msgbody:
            msg = self._conn.send(h11.Data(data=msgbody))
            assert msg is not None
            self._sock.sendall(msg)
        self._send_event(h11.EndOfMessage())

        resp_body: list = []
        error: Optional[HttpProtocolError] = None
        while True:
            ev = self._next_event()
            evt = type(ev)
            if evt is h11.EndOfMessage:
                if self._conn.our_state == h11.DONE and self._conn.their_state == h11.DONE:
                    self._conn.start_next_cycle()
                elif self._conn.our_state == h11.MUST_CLOSE:
                    self.close()
                else:
                    raise HttpProtocolError(
                        f"our state: {self._conn.our_state}, their state: {self._conn.their_state}")
                break
            elif evt is h11.ConnectionClosed:
                self.close()
                break
            elif evt is h11.Response:
                if ev.status_code == 302:
                    location = None
                    for header_name, header_value in ev.headers:
                        if header_name == b"location":
                            location = header_value.decode("ascii")
                        context = {
                            "location": location,
                            "method": method,
                            "path": path,
                            "data": data,
                            "content_type": content_type,
                            "fragment": fragment,
                            "query": query,
                            "params": params,
                        }
                    error = HttpProtocolRedirect(context)
                elif ev.status_code not in (200, 201, 304):
                    # Delay raising exception in this case to allow protocol to finish and collect
                    # body.
                    error = HttpResponseError(ev.status_code, ev.reason.decode("ascii"))
                resp_headers = list(ev.headers)
            elif evt is h11.Data:
                resp_body.append(ev.data)
        if error is not None:
            if resp_body:
                error.body = b"".join(resp_body)
            raise error
        if resp_body:
            resp_content_type = None
            for header_name, header_value in resp_headers:
                if header_name == b"content-type":
                    resp_content_type = header_value
                elif header_name == b"set-cookie":
                    self._cookie.load(header_value.decode("ascii"))
            return resp_headers, self.decode_content(resp_content_type, b"".join(resp_body))
        else:
            return resp_headers, b""

    def get_request(self,
                    path: str,
                    content_type: str = "text/html",
                    fragment: Optional[str] = None,
                    query: Optional[str] = None,
                    params: Optional[dict] = None):
        """Perform a GET request with path and optional query parameters."""
        return self._request("GET",
                             path=path,
                             data=None,
                             content_type=content_type,
                             fragment=fragment,
                             query=query,
                             params=params)

    def head_request(self,
                     path: str,
                     content_type: str = "*/*",
                     fragment: Optional[str] = None,
                     query: Optional[str] = None,
                     params: Optional[dict] = None):
        """Perform a HEAD request with path and optional query parameters."""
        return self._request("HEAD",
                             path=path,
                             data=None,
                             content_type=content_type,
                             fragment=fragment,
                             query=query,
                             params=params)

    def post_request(self,
                     path: str,
                     data: Any,
                     content_type: str,
                     fragment: Optional[str] = None,
                     query: Optional[str] = None,
                     params: Optional[dict] = None):
        """Perform a POST with path, data, content type, and optional query parameters."""
        return self._request("POST",
                             path=path,
                             data=data,
                             content_type=content_type,
                             fragment=fragment,
                             query=query,
                             params=params)

    def put_request(self, path: str, data: Any, content_type: str, params: Optional[dict] = None):
        """Perform a PUT with path, data, content type, and optional query parameters."""
        return self._request("PUT", path, data=data, content_type=content_type, params=params)

    def delete_request(self, path: str, params: Optional[dict] = None):
        """Perform a DELETE request with path and optional query parameters."""
        return self._request("DELETE", path, params=params)

    def download(self, path: str, filestream: BinaryIO, params: Optional[dict] = None):
        """Perform a GET and write body to filestream, with optional query parameters.

        Also computes the SHA256 checksum of downloaded content for comparison to externally
        provided checksum.

        Args:
            path: URL path component
            filestream: Binary writeable object.
            params: optional query parameters.

        Returns:
            headers, hexdigest
        """
        self._connect()
        headers = []
        hasher = hashlib.sha256()
        req_event = h11.Request(method="GET",
                                target=self.encode_target(path=path, params=params),
                                headers=self._headers)
        assert self._conn is not None
        assert self._sock is not None
        msg = self._conn.send(req_event)
        assert msg is not None
        self._sock.sendall(msg)
        self._send_event(h11.EndOfMessage())
        while True:
            ev = self._next_event()
            evt = type(ev)
            if evt is h11.EndOfMessage:
                if self._conn.our_state == h11.DONE and self._conn.their_state == h11.DONE:
                    self._conn.start_next_cycle()
                elif self._conn.our_state == h11.MUST_CLOSE:
                    self.close()
                else:
                    raise HttpProtocolError(
                        f"our state: {self._conn.our_state}, their state: {self._conn.their_state}")
                break
            elif evt is h11.ConnectionClosed:
                self.close()
                break
            elif evt is h11.Response:
                if ev.status_code not in (200, 201, 304):
                    raise HttpProtocolError(
                        f'Bad HTTP response, code: {ev.status_code} {ev.reason.decode("ascii")}')
                headers = list(ev.headers)
            elif evt is h11.Data:
                filestream.write(ev.data)
                hasher.update(ev.data)
        return headers, hasher.hexdigest()

    def decode_content(self, content_type, data):
        value, params = _parse_header_with_params(content_type)
        if b"json" in value:
            return json.decode_bytes(data)
        elif b"text/html" in value:
            charset = params.get(b"charset", b"utf-8")
            return data.decode(charset.decode("ascii"))
        else:
            raise HttpProtocolError(f"Unhandled receive content-type: {content_type}.")

    def encode_content(self, content_type: str, data: Any):
        if isinstance(data, bytes):  # allow for pre-encoded content.
            return data
        if "json" in content_type:
            return json.encode_bytes(data)
        else:
            raise HttpProtocolError(f"Unhandled encode content-type: {content_type}.")

    def encode_target(self,
                      path: Optional[str] = None,
                      fragment: Optional[str] = None,
                      query: Optional[str] = None,
                      params: Optional[dict] = None):
        url = builder.URIBuilder.from_uri(self._url.finalize())
        if path:
            url = url.add_path(path)
        if fragment:
            url = url.add_fragment(fragment)
        if query:
            url = url.add_query(query)
        if params:
            url = url.add_query_from(params)
        return url.finalize().unsplit()


def parse_url(urlstr):
    return rfc3986.urlparse(urlstr)


def _parse_header_with_params(text: bytes) -> Tuple[bytes, dict]:
    parts = text.split(b";")
    value = parts.pop(0).strip()
    params = {}
    for part in map(bytes.strip, parts):
        n, v = part.split(b"=", 1)
        if v.startswith(b'"'):
            params[n] = v[1:-1]
        else:
            params[n] = v
    return value, params


if __name__ == "__main__":
    c = SimpleWebInterface("https://www.google.com/", extra_headers=[("Accept", "*/*")])
    h, body = c.get_request("/")
    print(body)
    c.close()
