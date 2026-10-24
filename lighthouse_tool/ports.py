import argparse
import re
import urllib.parse
from typing import Dict, List, Optional, Tuple

LOWEST_PORT = 1
HIGHEST_PORT = 65535

PortPair = Tuple[int, int]


def port_number(text: str) -> int:
    if not text.isdigit() or not LOWEST_PORT <= int(text) <= HIGHEST_PORT:
        raise ValueError(text)
    return int(text)


def port_pair(text: str) -> PortPair:
    profile_port, separator, build_port = text.partition("=")
    try:
        if not separator:
            raise ValueError(text)
        return port_number(profile_port), port_number(build_port)
    except ValueError:
        raise argparse.ArgumentTypeError(
            "--port takes <profile port>=<build port>, each a whole number from {} to {}".format(LOWEST_PORT, HIGHEST_PORT)
        )


def port_map(pairs: Optional[List[PortPair]]) -> Dict[int, int]:
    return dict(pairs or [])


def with_build_ports(text: str, ports: Dict[int, int]) -> str:
    if not ports:
        return text
    profile_ports = "|".join(str(port) for port in sorted(ports, reverse=True))
    return re.sub(r"(?<!\d)({})(?!\d)".format(profile_ports), lambda found: str(ports[int(found.group(1))]), text)


def url_with_build_ports(url: str, ports: Dict[int, int]) -> str:
    parts = urllib.parse.urlsplit(url)
    if parts.port not in ports:
        return url
    host, _, _ = parts.netloc.rpartition(":")
    return parts._replace(netloc="{}:{}".format(host, ports[parts.port])).geturl()
