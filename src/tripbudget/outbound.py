import ipaddress
import socket
from urllib.parse import urlsplit

from .errors import DomainError

OFFICIAL_HOSTS = frozenset(
    {
        "www.metmuseum.org",
        "www.centralparknyc.org",
        "www.thehighline.org",
        "www.nyc.gov",
        "www.philamuseum.org",
        "www.nps.gov",
        "www.phlvisitorcenter.com",
        "naturalhistory.si.edu",
        "americanhistory.si.edu",
        "www.nga.gov",
        "www.spymuseum.org",
        "omny.info",
        "www.septa.org",
        "www.wmata.com",
    }
)


def validate_url(url: str):
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in OFFICIAL_HOSTS
        or parsed.port not in {None, 443}
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        raise DomainError("OUTBOUND_DENIED", "Only registered official HTTPS publishers are allowed", 403)
    # Actual fetch broker resolves only registered hosts, rejects unsafe results and follows no redirects.
    addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(x[4][0]).is_global for x in addresses):
        raise DomainError("OUTBOUND_DENIED", "Publisher resolved to a nonpublic address", 403)
    return url


def public_search_query(city, topic):
    if city not in {"NYC", "PHL", "DC"}:
        raise DomainError("OUTBOUND_DENIED", "Unsupported public city query", 403)
    # The topic is a server enum, not raw notes, request prose or model-selected text.
    topics = {
        "hours": "official museum attraction opening hours admission",
        "fares": "official transit fares passes",
    }
    if topic not in topics:
        raise DomainError("OUTBOUND_DENIED", "Unsupported public search purpose", 403)
    return f"{city} {topics[topic]}"
