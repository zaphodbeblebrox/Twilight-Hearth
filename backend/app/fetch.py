"""Download a web page that a member asked to import.

The address is untrusted. Only public internet addresses on the usual web ports are
contacted, checked when connecting so that redirects and changing DNS are covered too.
"""

import ipaddress
import socket
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpcore2
import httpx2
from fastapi import HTTPException

PORTS = {80, 443}
# Addresses that carry another, possibly private, IPv4 address inside them.
TUNNELS = [ipaddress.ip_network(n) for n in ("64:ff9b::/96", "2002::/16", "2001::/32")]
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; RecipeImporter/1.0)",
    "Accept": "text/html,application/xhtml+xml,application/pdf,image/*;q=0.9,*/*;q=0.5",
    "Accept-Language": "en",
    "Accept-Encoding": "gzip",
}


class Blocked(httpcore2.ConnectError):
    pass


@dataclass
class Page:
    url: str
    data: bytes
    encoding: str | None


def is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%")[0])
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    if ip.version == 6 and any(ip in network for network in TUNNELS):
        return False
    return ip.is_global and not ip.is_multicast


class DeadlineStream(httpcore2.NetworkStream):
    """Applies one time limit to the whole download rather than to each read."""

    def __init__(self, stream, deadline: float):
        self.stream, self.deadline = stream, deadline

    def left(self) -> float:
        left = self.deadline - time.monotonic()
        if left <= 0:
            raise httpcore2.ReadTimeout("Took too long")
        return left

    def read(self, max_bytes, timeout=None):
        return self.stream.read(max_bytes, self.left())

    def write(self, buffer, timeout=None):
        self.stream.write(buffer, self.left())

    def close(self):
        self.stream.close()

    def start_tls(self, ssl_context, server_hostname=None, timeout=None):
        stream = self.stream.start_tls(ssl_context, server_hostname, self.left())
        return DeadlineStream(stream, self.deadline)

    def get_extra_info(self, info):
        return self.stream.get_extra_info(info)


class PublicBackend(httpcore2.SyncBackend):
    def __init__(self, deadline: float):
        self.deadline = deadline

    def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        if port not in PORTS:
            raise Blocked("Port not allowed")
        try:
            found = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except (OSError, UnicodeError) as error:
            raise httpcore2.ConnectError(str(error)) from error
        addresses = list(dict.fromkeys(str(info[4][0]) for info in found))
        if not addresses or not all(is_public(a) for a in addresses):
            raise Blocked("Address not allowed")
        # Prefer IPv4, which every network has, and connect to exactly what was checked.
        addresses = sorted(addresses, key=lambda a: ":" in a)[:3]
        for address in addresses:
            left = self.deadline - time.monotonic()
            if left <= 0:
                break
            try:
                stream = super().connect_tcp(
                    address, port, min(left, 5), local_address, socket_options
                )
                return DeadlineStream(stream, self.deadline)
            except (httpcore2.ConnectError, httpcore2.ConnectTimeout):
                continue
        raise httpcore2.ConnectError("Could not connect")


def check_url(url: str) -> str:
    url = url.strip()
    if "://" not in url:
        url = f"https://{url}"
    try:
        parts = urlsplit(url)
        valid = parts.scheme in ("http", "https") and parts.hostname and not parts.username
    except ValueError:
        valid = False
    if not valid:
        raise HTTPException(422, "Enter a web address such as https://example.com/recipe")
    return url


def fetch(url: str, *, max_bytes: int, seconds: float) -> Page:
    deadline = time.monotonic() + seconds
    transport = httpx2.HTTPTransport(trust_env=False)
    # HTTPTransport has no option for this. test_private_addresses_are_refused guards it.
    transport._pool = httpcore2.ConnectionPool(
        ssl_context=httpx2.create_ssl_context(trust_env=False),
        network_backend=PublicBackend(deadline),
    )
    try:
        with (
            httpx2.Client(
                transport=transport,
                trust_env=False,
                follow_redirects=True,
                max_redirects=5,
                timeout=seconds,
                headers=HEADERS,
            ) as client,
            client.stream("GET", url) as response,
        ):
            if response.status_code != 200:
                raise HTTPException(
                    422,
                    f"That site would not share the page (error {response.status_code}). "
                    "Save the page as a PDF or take a screenshot, then import the file.",
                )
            data = bytearray()
            for chunk in response.iter_bytes():
                data += chunk
                if len(data) > max_bytes:
                    raise HTTPException(422, "That page is too large to import")
            return Page(str(response.url), bytes(data), response.charset_encoding)
    except (httpx2.HTTPError, httpx2.InvalidURL, ValueError):
        raise HTTPException(422, "Could not open that web address") from None
