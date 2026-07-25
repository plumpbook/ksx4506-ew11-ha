from __future__ import annotations

import ipaddress
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
IPV4_RE = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
DOCUMENTATION_NETS = tuple(
    ipaddress.ip_network(value)
    for value in (
        "192.0.2.0/24",
        "198.51.100.0/24",
        "203.0.113.0/24",
    )
)
CGNAT_NET = ipaddress.ip_network(".".join(("100", "64", "0", "0")) + "/10")
LOCAL_ENVIRONMENT_MARKERS = tuple(
    "".join(parts)
    for parts in (
        ("home", ".", "code", ".", "band"),
        ("mastar", "-", "nas"),
        ("UJunguic", "BookPro"),
        ("/", "volume1", "/"),
    )
)
BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico"}


def _repository_files() -> list[Path]:
    output = subprocess.check_output(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
    )
    return [
        ROOT / item.decode()
        for item in output.split(b"\0")
        if item and (ROOT / item.decode()).suffix.lower() not in BINARY_SUFFIXES
    ]


def _is_documentation_ip(ip: ipaddress.IPv4Address) -> bool:
    return any(ip in network for network in DOCUMENTATION_NETS)


def test_public_artifacts_do_not_contain_local_environment_identifiers():
    findings: list[str] = []

    for path in _repository_files():
        rel_path = path.relative_to(ROOT)
        text = path.read_text(encoding="utf-8", errors="ignore")

        for marker in LOCAL_ENVIRONMENT_MARKERS:
            if marker.lower() in text.lower():
                findings.append(f"{rel_path}: contains local marker {marker!r}")

        for match in IPV4_RE.finditer(text):
            line_start = text.rfind("\n", 0, match.start()) + 1
            line_end = text.find("\n", match.end())
            if line_end == -1:
                line_end = len(text)
            if path.name == "uv.lock" and text[line_start:line_end].lstrip().startswith(
                "version = "
            ):
                continue
            value = match.group(0)
            try:
                ip = ipaddress.IPv4Address(value)
            except ValueError:
                continue
            if _is_documentation_ip(ip):
                continue
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip in CGNAT_NET
            ):
                findings.append(f"{rel_path}: contains local/private IP {value}")

    assert findings == []
