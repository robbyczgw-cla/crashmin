"""Guardrails so the public repo cannot grow a real capture by accident."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from crashmin.cli import main
from crashmin.models import HttpRequest

ROOT = Path(__file__).resolve().parents[1]

# Files we ship. Skip venv / caches if someone runs pytest from a dirty tree.
SHIP_SUFFIXES = {".py", ".md", ".curl", ".http", ".har", ".yml", ".toml", ".sh"}
SKIP_PARTS = {".git", ".venv", ".pytest_cache", "__pycache__", "egg-info"}

JWT_HEADER = re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.")
GITHUB_TOKEN = re.compile(r"ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}")
PRIVATE_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@(?!example\.invalid\b)(?!local\b)[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
ALLOWED_HOST_RE = re.compile(
    r"https?://([A-Za-z0-9._-]+)",
    re.IGNORECASE,
)
ALLOWED_HOSTS = {
    "127.0.0.1",
    "localhost",
    "example.com",  # only as the host we *refuse*
    "intranet.example.invalid",
    "app.example.invalid",
    "github.com",
    "noperator",  # leftover from markdown links? handled via full netloc
}


def _ship_files():
    import subprocess

    listed = subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True)
    for line in listed.splitlines():
        path = ROOT / line
        if path.suffix in SHIP_SUFFIXES and path.is_file():
            yield path


def test_no_jwt_lookalikes_in_tree():
    hits = []
    for path in _ship_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        if JWT_HEADER.search(text):
            hits.append(str(path.relative_to(ROOT)))
    assert hits == []


def test_no_github_tokens_in_tree():
    hits = []
    for path in _ship_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        if GITHUB_TOKEN.search(text):
            hits.append(str(path.relative_to(ROOT)))
    assert hits == []


def test_demo_hosts_are_reserved():
    from crashmin.demo import build_killer_request

    req = build_killer_request("http://127.0.0.1:9")
    assert req.host == "127.0.0.1"
    assert "example.invalid" in (req.header_value("Origin") or "")
    assert "not-a-real-jwt" in (req.header_value("Authorization") or "")
    assert "eyJ" not in (req.header_value("Authorization") or "")


def test_progress_log_omits_query_and_cookies(tmp_path, capsys):
    path = tmp_path / "req.curl"
    path.write_text(
        "curl 'http://127.0.0.1:1/x?session=super-secret' "
        "-H 'Cookie: sid=leaked' -H 'Authorization: Bearer leaked-token'\n",
        encoding="utf-8",
    )
    main([str(path), "--status", "500"])
    err = capsys.readouterr().err
    assert "super-secret" not in err
    assert "sid=leaked" not in err
    assert "leaked-token" not in err
    assert "127.0.0.1" in err


def test_log_target_strips_query():
    req = HttpRequest()
    req.set_url("http://127.0.0.1/x?session=super-secret")
    req.cookies = [("sid", "leaked")]
    text = req.log_target()
    assert "super-secret" not in text
    assert "leaked" not in text
    assert "1 query" in text
    assert "1 cookies" in text


def test_sample_requests_only_use_reserved_hosts():
    """Corpus / examples / generators must not name a real site as the target."""
    allowed = {"127.0.0.1", "localhost"}
    allowed_suffix = ".invalid"
    scan_roots = [
        ROOT / "corpus",
        ROOT / "examples",
        ROOT / "src" / "crashmin" / "demo.py",
        ROOT / "src" / "crashmin" / "corpus.py",
        ROOT / "src" / "crashmin" / "fixtures.py",
    ]
    bad = []
    files = []
    for root in scan_roots:
        if root.is_file():
            files.append(root)
        elif root.is_dir():
            files.extend(p for p in root.rglob("*") if p.is_file())
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in ALLOWED_HOST_RE.finditer(text):
            host = match.group(1).split(":")[0].lower()
            if host in allowed or host.endswith(allowed_suffix):
                continue
            bad.append(f"{path.relative_to(ROOT)}: {host}")
    assert bad == []
