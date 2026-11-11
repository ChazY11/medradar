"""TLS chain completion for servers that omit their intermediate certificate.

Problem
-------
``opic-cipo.ca`` (Canadian Intellectual Property Office bulk downloads) serves
only its leaf certificate and omits the issuing intermediate. Browsers recover
by fetching the intermediate from the AIA ``caIssuers`` URL printed in the leaf
and retrying; Python's ``ssl`` module does not chase AIA, so ``requests`` fails
with ``unable to get local issuer certificate``.

What this module does — and deliberately does not do
---------------------------------------------------
It performs the *same* recovery a browser performs: read the leaf, follow its
``AuthorityInformationAccess`` ``caIssuers`` pointers, download the public
intermediate certificate(s), and build a CA bundle consisting of the platform
trust bundle **plus** those intermediates. Verification is then performed
normally against the platform roots.

It never sets ``verify=False``, never disables hostname checking, and never
pins a certificate obtained out of band. If the resulting chain does not
validate to a trusted root, the fetch fails like any other TLS failure.
"""

from __future__ import annotations

import hashlib
import os
import socket
import ssl
from dataclasses import dataclass

import requests


@dataclass
class ChainResult:
    host: str
    ok: bool
    leaf_subject: str | None = None
    leaf_issuer: str | None = None
    intermediates: list[str] | None = None
    ai_uris: list[str] | None = None
    bundle_path: str | None = None
    error: str | None = None


def _leaf_der(host: str, port: int = 443, timeout: float = 25.0) -> bytes:
    ctx = ssl._create_unverified_context()
    with socket.create_connection((host, port), timeout=timeout) as sock:
        with ctx.wrap_socket(sock, server_hostname=host) as ss:
            deriv = ss.getpeercert(binary_form=True)
    if not deriv:
        raise RuntimeError(f"{host}: server returned no certificate")
    return deriv


def _aia_ca_issuers(der: bytes) -> list[str]:
    from cryptography import x509
    from cryptography.hazmat.backends import default_backend
    from cryptography.x509.oid import AuthorityInformationAccessOID

    cert = x509.load_der_x509_certificate(der, default_backend())
    uris: list[str] = []
    try:
        aia = cert.extensions.get_extension_for_class(x509.AuthorityInformationAccess)
    except x509.ExtensionNotFound:
        return uris
    for desc in aia.value:
        if desc.access_method == AuthorityInformationAccessOID.CA_ISSUERS:
            loc = desc.access_location
            if isinstance(loc, x509.UniformResourceIdentifier):
                uris.append(loc.value)
    return uris


def _cert_names(der: bytes) -> tuple[str, str]:
    from cryptography import x509

    cert = x509.load_der_x509_certificate(der)
    return (
        cert.subject.rfc4514_string(),
        cert.issuer.rfc4514_string(),
    )


def complete_chain(
    host: str,
    cache_dir: str,
    *,
    max_depth: int = 3,
    timeout: float = 30.0,
) -> ChainResult:
    """Build ``<cache_dir>/<host>.bundle.pem`` = certifi roots + intermediates."""
    os.makedirs(cache_dir, exist_ok=True)
    try:
        leaf = _leaf_der(host, timeout=timeout)
    except Exception as exc:
        return ChainResult(host=host, ok=False, error=f"{type(exc).__name__}: {exc}"[:300])

    try:
        subject, issuer = _cert_names(leaf)
        uris = _aia_ca_issuers(leaf)
    except Exception as exc:
        return ChainResult(host=host, ok=False, error=f"cert parse failed: {exc}"[:300])

    collected: list[bytes] = []
    seen: set[str] = set()
    frontier = list(uris)
    depth = 0
    fetch_err: list[str] = []
    while frontier and depth < max_depth and len(collected) < max_depth:
        nxt: list[str] = []
        for uri in frontier:
            if uri in seen:
                continue
            seen.add(uri)
            try:
                r = requests.get(uri, timeout=timeout)
                if r.status_code != 200 or not r.content:
                    fetch_err.append(f"{uri}: HTTP {r.status_code}")
                    continue
                body = r.content
                # tolerate PEM or DER
                if b"-----BEGIN CERTIFICATE-----" in body:
                    from cryptography import x509
                    from cryptography.hazmat.primitives.serialization import Encoding
                    pem_certs = x509.load_pem_x509_certificates(body)
                    ders = [c.public_bytes(Encoding.DER) for c in pem_certs]
                else:
                    ders = [body]
                for der in ders:
                    if der not in collected:
                        collected.append(der)
                    try:
                        nxt.extend(_aia_ca_issuers(der))
                    except Exception:
                        pass
            except Exception as exc:
                fetch_err.append(f"{uri}: {type(exc).__name__}")
        frontier = nxt
        depth += 1

    if not collected:
        return ChainResult(
            host=host,
            ok=False,
            leaf_subject=subject,
            leaf_issuer=issuer,
            ai_uris=uris,
            error="no intermediate certificate could be retrieved from AIA: "
            + "; ".join(fetch_err)[:200],
        )

    import certifi
    from cryptography.hazmat.primitives.serialization import Encoding

    bundle_path = os.path.join(cache_dir, f"{host}.bundle.pem")
    with open(certifi.where(), "rb") as fh:
        platform_roots = fh.read()
    with open(bundle_path, "wb") as fh:
        fh.write(platform_roots.rstrip() + b"\n")
        for der in collected:
            from cryptography import x509

            fh.write(x509.load_der_x509_certificate(der).public_bytes(Encoding.PEM))
            fh.write(b"\n")

    # verify the rebuilt chain actually works, with normal hostname checking
    try:
        ctx = ssl.create_default_context()
        ctx.load_verify_locations(cafile=bundle_path)
        with socket.create_connection((host, 443), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=host):
                pass
        ok = True
        err = None
    except Exception as exc:
        ok = False
        err = f"rebuilt chain still fails verification: {type(exc).__name__}: {exc}"[:300]

    names = []
    for der in collected:
        try:
            names.append(_cert_names(der)[0])
        except Exception:
            names.append("<unparsed certificate>")

    return ChainResult(
        host=host,
        ok=ok,
        leaf_subject=subject,
        leaf_issuer=issuer,
        intermediates=names,
        ai_uris=uris,
        bundle_path=bundle_path if ok else None,
        error=err,
    )


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
