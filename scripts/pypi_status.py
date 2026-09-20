"""Check whether continuum-history exists on PyPI. Network; not in the foundation gate."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

PROJECT = "continuum-history"
JSON_URL = f"https://pypi.org/pypi/{PROJECT}/json"
PENDING_PUBLISHER = "https://pypi.org/manage/account/publishing/"
LOCKED = {
    "PyPI project name": PROJECT,
    "Owner": "bosprimigenious",
    "Repository": "continuum",
    "Workflow filename": "publish.yml",
    "Environment name": "pypi",
}


def main() -> int:
    print("Pending publisher fields (must match OIDC claims):")
    for key, value in LOCKED.items():
        print(f"  {key}: {value}")
    print(f"Register at: {PENDING_PUBLISHER}")
    request = urllib.request.Request(JSON_URL, headers={"User-Agent": "continuum-pypi-status"})
    proxy = (
        os.environ.get("HTTPS_PROXY")
        or os.environ.get("https_proxy")
        or os.environ.get("ALL_PROXY")
        or os.environ.get("all_proxy")
    )
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": proxy, "https": proxy})
        if proxy
        else urllib.request.ProxyHandler({})
    )
    try:
        with opener.open(request, timeout=30) as response:
            payload = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"NOT READY: {JSON_URL} -> HTTP {exc.code} {body[:200]!r}", file=sys.stderr)
        print(
            "PyPI has no project yet. A GitHub OIDC 422 invalid-publisher means the "
            "pending publisher is missing or the Environment name is not 'pypi'. "
            "Do not bump 0.1.0a1 to retry. See docs/publishing.md.",
            file=sys.stderr,
        )
        return 2
    except urllib.error.URLError as exc:
        print(f"NOT READY: could not reach PyPI ({exc})", file=sys.stderr)
        return 2
    version = payload.get("info", {}).get("version")
    print(f"PASS: {PROJECT} is on PyPI (info.version={version!r})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
