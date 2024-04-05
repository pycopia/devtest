# python3
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Additional URI parsing functions. This module extends the stock urlparse module
and you can use it in place of that module.

"""

from urllib.parse import *  # noqa
import functools
import re

# Well known service ports.
# Using getservbyname is unreliable across hosts (some say port 80 is "www")
SERVICES = {
    "ftp": 21,
    "ssh": 22,
    "telnet": 23,
    "smtp": 25,
    "gopher": 70,
    "http": 80,
    "nntp": 119,
    "imap": 143,
    "prospero": 191,
    "wais": 210,
    "https": 443,
    "rtsp": 554,
    "rsync": 873,
    "ftps": 990,
    "imaps": 993,
    "svn": 3690,
    "postgres": 5432,
    "mysql": 3306,
    "sqlite": 0,
}

SERVICES_REVERSE = dict((v, k) for k, v in list(SERVICES.items()))

# from rfc2396 appendix B:
URI_RE_STRICT = r"^(([^:/?#]+):)?(//([^/?#]*))?([^?#]*)(\?([^#]*))?(#(.*))?"
URI_RE_STRICT = re.compile(URI_RE_STRICT)

# But, this is better for finding URL embedded in a string.
URI_RE = (r"((\w+)://){1}"
          r"([^/?#]*)"
          r"(/[;/:@&=+$,._%A-Za-z0-9]*)"
          r"(\?([;/?:@&=+$,-_.!~*'()%A-Za-z0-9]*))?"
          r"(#(\w*))?")
URI_RE = re.compile(URI_RE)

# char-classes:
# uric        = r";/?:@&=+$,-_.!~*'()A-Za-z0-9%"
# pchar       = r":@&=+$," # | unreserved | escaped
# reserved    = r";/?:@&=+$,"
# unreserved  = alphanum | mark
# mark        = r"-_.!~*'()"
# alphanum    = r"A-Za-z0-9"
# escaped     = r"%A-Fa-f0-9"


@functools.lru_cache(maxsize=32)
def uriparse(uri, strict=False):
    """Given a valid URI, return a 5-tuple of (scheme, authority, path,
    query, fragment). The query part is a URLQuery object, the rest are
    strings.
    Raises ValueError if URI is malformed.
    """
    if strict:
        mo = URI_RE_STRICT.search(uri)
        if mo:
            _, scheme, _, authority, path, _, query, _, fragment = mo.groups()
        else:
            raise ValueError("Invalid URI: %r" % (uri,))
    else:
        mo = URI_RE.search(uri)
        if mo:
            _, scheme, authority, path, _, query, _, fragment = mo.groups()
        else:
            raise ValueError("Invalid URI: %r" % (uri,))
    if query:
        q = queryparse(query)
    else:
        q = URLQuery()
    return (scheme, authority, path, q, fragment)


def urimatch(uri, strict=False):
    """Return a re.MatchObject (or None) depending on if the uri string matches
    a URI pattern.
    """
    if strict:
        return URI_RE_STRICT.match(uri)
    else:
        return URI_RE.search(uri)


def serverparse(server):
    """serverparse(serverpart)
    Parses a server part and returns a 4-tuple (user, password, host, port). """
    user = password = host = port = None
    server = server.split("@", 1)
    if len(server) == 2:
        userinfo, hostport = server
        userinfo = userinfo.split(":", 1)
        if len(userinfo) == 2:
            user, password = userinfo
        else:
            user = userinfo[0]
        server = server[1]
    else:
        server = server[0]
    server = server.split(":", 1)
    if len(server) == 2:
        host, port = server
    else:
        host = server[0]
    return user, password, host, port


def paramparse(params):
    return params.split(";")


def queryparse(query, evaluator=lambda x: x):
    q = URLQuery()
    parts = query.split("&")
    for part in parts:
        if part:
            try:
                l, r = part.split("=", 1)
            except ValueError:
                l, r = part, ""
            key = unquote_plus(l)
            val = evaluator(unquote_plus(r))
            q[key] = val
    return q


class URLQuery(dict):
    """Dictionary for holding query parameters.

    This can handle multiple values for the same key.
    """

    def __init__(self, init=()):
        if isinstance(init, str):
            init = queryparse(init)
        dict.__init__(self, init)

    def __str__(self):
        return urlencode(self, 1)

    def __repr__(self):
        return "%s(%r)" % (self.__class__.__name__, list(self.items()))

    # This setitem enforces the "contract" that values are strings or list
    # of strings.
    def __setitem__(self, key, val):
        if key in self:
            kv = dict.__getitem__(self, key)
            if isinstance(kv, list):
                if isinstance(val, list):
                    kv.extend(list(map(str, val)))
                else:
                    kv.append(str(val))
            else:
                dict.__setitem__(self, key, [kv, str(val)])
        else:
            if isinstance(val, list):
                dict.__setitem__(self, key, list(map(str, val)))
            else:
                dict.__setitem__(self, key, str(val))

    def __getitem__(self, key):
        val = dict.__getitem__(self, key)
        if isinstance(val, list):
            return val[:]
        else:
            return val

    def __delitem__(self, key):
        val = dict.__getitem__(self, key)
        if isinstance(val, list):
            del val[-1]
            if not val:
                dict.__delitem__(self, key)
            if len(val) == 1:
                v = val[0]
                dict.__setitem__(self, key, v)
            return
        dict.__delitem__(self, key)

    def getlist(self, key):
        try:
            val = dict.__getitem__(self, key)
        except KeyError:
            return []
        if isinstance(val, list):
            return val
        else:
            return [val]

    def update(self, other):
        if isinstance(other, str):
            other = queryparse(other)
        dict.update(self, other)

    # semi-deep copy since the values here will only be strings, or a list
    # of strings (only). A complete deepcopy implementation is not
    # necessary.
    def copy(self):
        new = self.__class__()
        for k, v in list(self.items()):
            if isinstance(v, list):
                new[k] = v[:]
            else:
                new[k] = v
        return new


class UniversalResourceLocator:
    """A general purpose URL object. Parse and generate URLs.
    Provided for read-parse-modify-write operations on URL strings.
    """

    def __init__(self, url=None, strict=True):
        if url:
            self.set(url, strict)
        else:
            self.clear(strict)

    def clear(self, strict=True):
        self._strict = strict
        self._urlstr = ""
        self._badurl = True
        # URL components
        self._scheme = None
        self._user = self._password = self._host = None
        self._port = 0
        self._path = None
        self._params = []
        self._query = URLQuery()
        self._fragment = None

    def __bool__(self):
        return bool(self._scheme)  # valid url has scheme.

    def set(self, url, strict=True):
        if isinstance(url, str):
            # URL's are defined to be in the ASCII character set.
            url = quote(url, ";/?:@&=+$,")
            self.clear(strict)
            try:
                self._parse(url, strict)
            except ValueError:
                self.clear(strict)
                raise
            else:
                self._urlstr = url
                self._badurl = False
        elif isinstance(url, self.__class__):
            self._set_from_instance(url)
        else:
            raise ValueError("Invalid initializer: %r" % (url,))

    def _parse(self, url, strict):
        self._scheme, netloc, self._path, self._query, self._fragment = uriparse(url, strict)
        self._user, self._password, self._host, port = serverparse(netloc)
        if port is not None:
            self._port = int(port)
        else:
            self._port = SERVICES.get(self._scheme, 0)

    def _set_from_instance(self, other):
        self.__dict__.update(other.__dict__)
        self._params = other._params[:]
        self._query = other._query.copy()
        self._badurl = True

    def __repr__(self):
        return "%s(%r, %r)" % (self.__class__.__name__, self.__str__(), self._strict)

    def __str__(self):
        if not self._badurl:
            return self._urlstr
        if self._scheme is None:
            return ""
        s = [self._scheme, "://"]
        if self._host:
            s.append(self._host)
            if self._user:
                if self._password:
                    s.insert(2, "%s:%s" % (self._user, self._password))
                else:
                    s.insert(2, self._user)
                s.insert(3, "@")
            if self._port and SERVICES_REVERSE.get(self._port, "") != self._scheme:
                s.append(":")
                s.append(str(self._port))
        if self._path:
            s.append(self._path)
        if self._params:
            s.append(";")
            s.append(";".join(self._params))
        if self._query:
            s.append("?")
            s.append(urlencode(self._query, True))
        if self._fragment:
            s.append("#")
            s.append(self._fragment)
        url = "".join(s)
        self._urlstr = url
        self._badurl = False
        return url

    def __iter__(self):
        return iter(self.__str__())

    def __add__(self, other):
        my_s = self.__str__()
        new_s = my_s + str(other)
        return self.__class__(new_s)

    def __iadd__(self, other):
        my_s = self.__str__()
        new_s = my_s + str(other)
        self.set(new_s, self._strict)
        return self

    def __mod__(self, params):
        new = self.__class__(self)
        new.path = new.path % params  # other parts?
        return new

    def copy(self):
        return self.__class__(self)

    def _set_URL(self, url):
        self.set(url, self._strict)

    def set_scheme(self, name):
        self._badurl = True
        self._scheme = name

    def set_user(self, name):
        self._badurl = True
        self._user = name

    def del_user(self):
        if self._user:
            self._badurl = True
            self._user = None

    def set_password(self, name):
        self._badurl = True
        self._password = name

    def del_password(self):
        if self._password:
            self._badurl = True
            self._password = None

    def set_host(self, name):
        self._badurl = True
        self._host = name

    def del_host(self):
        self._badurl = True
        self._host = None

    def set_port(self, name):
        self._badurl = True
        self._port = int(name)

    def del_port(self):
        if self._port:
            self._badurl = True
            self._port = SERVICES.get(self._scheme, 0)  # set to default

    def set_path(self, name):
        self._badurl = True
        self._path = name

    def del_path(self):
        self._badurl = True
        self._path = None

    def get_query(self):
        self._badurl = True  # assume you are going to change it.
        return self._query

    def set_query(self, data, update=True):
        self._badurl = True
        if data is None:
            self._query.clear()
        else:
            if update:
                self._query.update(data)
            else:
                self._query = URLQuery(data)

    def del_query(self):
        self._badurl = True
        self._query.clear()

    def set_fragment(self, data):
        self._badurl = True
        self._fragment = str(data)

    def del_fragment(self):
        if self._fragment:
            self._badurl = True
            self._fragment = None

    def set_params(self, params):
        assert isinstance(params, list)
        self._badurl = True
        self._params = params

    def del_params(self):
        if self._params:
            self._badurl = True
            self._params = []

    def get_address(self):
        """Return address suitable for a socket."""
        return (self._host, self._port)

    URL = property(__str__, _set_URL, None, "Full URL")
    scheme = property(lambda s: s._scheme, set_scheme, None, "Scheme part")
    user = property(lambda s: s._user, set_user, del_user, "User part")
    password = property(lambda s: s._password, set_password, del_password, "Password part")
    host = property(lambda s: s._host, set_host, del_host, "Host part ")
    port = property(lambda s: s._port, set_port, del_port, "Port part ")
    path = property(lambda s: s._path, set_path, del_path, "Path part ")
    params = property(lambda s: s._params, set_params, del_params, "Params part")
    query = property(get_query, set_query, del_query, "URLQuery object")
    fragment = property(lambda s: s._fragment, set_fragment, del_fragment, "Fragment part")
    address = property(get_address)


if __name__ == "__main__":
    URL = "http://name:pass@www.host.com:8080/cgi?qr=arg1&qr=arg2&arg3=val3"
    uURL = "http://name:pass@www.host.com:8080/cgi?qr=arg1&qr=arg2&arg3=val3"
    url = UniversalResourceLocator(URL)
    print(url)
    uurl = UniversalResourceLocator(uURL)
    assert str(url) == str(uurl)
    assert url.scheme == "http"
    assert url.user == "name"
    assert url.password == "pass"
    assert url.host == "www.host.com"
    assert url.port == 8080
    assert url.path == "/cgi"
    assert url.params == []
    assert url.fragment is None
    assert str(url) == URL
    url.scheme = "https"
    url.query["arg4"] = "val4"
    # assert str(url) == ("https://name:pass@www.host.com:8080/cgi"
    #                     "?arg3=val3&qr=arg1&qr=arg2&arg4=val4")
    assert url.host == "www.host.com"
    url2 = UniversalResourceLocator(url)
    del url.query
    del url2.query
    assert str(url2) == str(url)

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab:fileencoding=utf-8
