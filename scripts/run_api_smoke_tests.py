#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


SERIES_SLUG = "One-piece-Edition-originale"
SERIES_URL = "https://www.manga-news.com/index.php/serie/One-piece-Edition-originale"
VOLUME_SERIES_SLUG = "One-Piece"
VOLUME_SLUG = "vol-91"
VOLUME_URL = "https://www.manga-news.com/index.php/manga/One-Piece/vol-91"


class TestFailure(Exception):
    pass


class ApiRunner:
    def __init__(self, base_url: str, token: str | None, admin_token: str | None, timeout: float, output_dir: Path | None):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.admin_token = admin_token or token
        self.timeout = timeout
        self.output_dir = output_dir
        self.etag: str | None = None
        self.failures: list[str] = []
        self.passes = 0

    def _headers(self, *, json_body: bool = False, if_none_match: str | None = None, admin: bool = False) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json"}
        bearer = self.admin_token if admin else self.token
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"
        if json_body:
            headers["Content-Type"] = "application/json"
        if if_none_match:
            headers["If-None-Match"] = if_none_match
        return headers

    def _request(
        self,
        name: str,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        if_none_match: str | None = None,
        admin: bool = False,
    ) -> tuple[int, dict[str, str], bytes]:
        url = f"{self.base_url}{path}"
        if params:
            query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
            url = f"{url}?{query}"
        data = None
        headers = self._headers(json_body=json_body is not None, if_none_match=if_none_match, admin=admin)
        if json_body is not None:
            data = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(url=url, method=method.upper(), data=data, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read()
                response_headers = {key: value for key, value in response.headers.items()}
                status = response.status
        except urllib.error.HTTPError as exc:
            body = exc.read()
            response_headers = {key: value for key, value in exc.headers.items()}
            status = exc.code
        except urllib.error.URLError as exc:
            raise TestFailure(f"{name}: réseau / connexion impossible: {exc}") from exc

        self._save_output(name, status, response_headers, body)
        return status, response_headers, body

    def _save_output(self, name: str, status: int, headers: dict[str, str], body: bytes) -> None:
        if not self.output_dir:
            return
        safe_name = name.lower().replace(" ", "_")
        payload: dict[str, Any] = {
            "status": status,
            "headers": headers,
        }
        text_body = body.decode("utf-8", errors="replace") if body else ""
        try:
            payload["body"] = json.loads(text_body) if text_body else None
        except json.JSONDecodeError:
            payload["body_text"] = text_body
        (self.output_dir / f"{safe_name}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _assert(self, condition: bool, message: str) -> None:
        if not condition:
            raise TestFailure(message)

    def _assert_common_headers(self, name: str, headers: dict[str, str], *, expect_cache_headers: bool = True) -> None:
        self._assert("X-Request-ID" in headers, f"{name}: X-Request-ID manquant")
        if expect_cache_headers:
            self._assert("ETag" in headers, f"{name}: ETag manquant")
            self._assert("X-Data-Fingerprint" in headers, f"{name}: X-Data-Fingerprint manquant")
            self._assert("X-Cache-Status" in headers, f"{name}: X-Cache-Status manquant")

    def _json(self, name: str, body: bytes) -> dict[str, Any]:
        try:
            return json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise TestFailure(f"{name}: corps JSON invalide") from exc

    def run(
        self,
        name: str,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        expect_status: int = 200,
        validator=None,
        if_none_match: str | None = None,
        expect_cache_headers: bool = True,
        admin: bool = False,
    ) -> None:
        try:
            status, headers, body = self._request(name, method, path, params=params, json_body=json_body, if_none_match=if_none_match, admin=admin)
            self._assert(status == expect_status, f"{name}: statut {status} au lieu de {expect_status}")
            if expect_status != 304:
                self._assert_common_headers(name, headers, expect_cache_headers=expect_cache_headers)
            if validator is not None:
                validator(status, headers, body)
        except TestFailure as exc:
            self.failures.append(str(exc))
            print(f"[FAIL] {exc}")
            return
        self.passes += 1
        print(f"[OK]   {name}")


runner: ApiRunner


def validate_ok(name: str, expected_path: list[str] | None = None, expected_value: Any | None = None):
    def _validator(status: int, headers: dict[str, str], body: bytes) -> None:
        payload = runner._json(name, body)
        if payload.get("ok") is not True:
            raise TestFailure(f"{name}: ok != true")
        if expected_path is not None:
            current: Any = payload
            rendered_path = '/'.join(str(part) for part in expected_path)
            for part in expected_path:
                if isinstance(part, int):
                    if not isinstance(current, list) or part >= len(current):
                        raise TestFailure(f"{name}: chemin manquant {rendered_path}")
                    current = current[part]
                    continue
                if not isinstance(current, dict) or part not in current:
                    raise TestFailure(f"{name}: chemin manquant {rendered_path}")
                current = current[part]
            if expected_value is not None and current != expected_value:
                raise TestFailure(f"{name}: valeur inattendue pour {rendered_path} -> {current!r} != {expected_value!r}")
    return _validator


def validate_lookup(status: int, headers: dict[str, str], body: bytes) -> None:
    payload = runner._json("lookup volume", body)
    data = payload.get("data") or {}
    resolved = data.get("resolved") or {}
    volume = data.get("volume") or {}
    if resolved.get("series_slug") != VOLUME_SERIES_SLUG:
        raise TestFailure(f"lookup volume: mauvais series_slug {resolved.get('series_slug')!r}")
    if resolved.get("volume_slug") != VOLUME_SLUG:
        raise TestFailure(f"lookup volume: mauvais volume_slug {resolved.get('volume_slug')!r}")
    if str(volume.get("number")) != "91":
        raise TestFailure(f"lookup volume: mauvais number {volume.get('number')!r}")



def validate_volume(status: int, headers: dict[str, str], body: bytes) -> None:
    payload = runner._json("volume", body)
    data = payload.get("data") or {}
    if str(data.get("number")) != "91":
        raise TestFailure(f"volume: number inattendu {data.get('number')!r}")
    if data.get("number_int") != 91:
        raise TestFailure(f"volume: number_int inattendu {data.get('number_int')!r}")
    if data.get("publisher_fr") != "Glénat":
        raise TestFailure(f"volume: publisher_fr inattendu {data.get('publisher_fr')!r}")
    if data.get("publication_date") != "2019-07-03":
        raise TestFailure(f"volume: publication_date inattendue {data.get('publication_date')!r}")
    if data.get("isbn_ean") != "9782344037102":
        raise TestFailure(f"volume: isbn_ean inattendu {data.get('isbn_ean')!r}")



def validate_series(status: int, headers: dict[str, str], body: bytes) -> None:
    payload = runner._json("series", body)
    data = payload.get("data") or {}
    if data.get("title") != "One Piece":
        raise TestFailure(f"series: title inattendu {data.get('title')!r}")
    runner.etag = headers.get("ETag")



def validate_304(status: int, headers: dict[str, str], body: bytes) -> None:
    if status != 304:
        raise TestFailure(f"etag: statut inattendu {status}")
    if body not in {b"", b"null"}:
        raise TestFailure("etag: le corps devrait être vide pour un 304")


def validate_metrics(status: int, headers: dict[str, str], body: bytes) -> None:
    payload = runner._json("admin metrics", body)
    data = payload.get("data") or {}
    counters = data.get("counters") or {}
    ratios = data.get("ratios") or {}
    if "responses_total" not in counters:
        raise TestFailure("admin metrics: compteur responses_total manquant")
    if "cache_hit_ratio" not in ratios:
        raise TestFailure("admin metrics: ratio cache_hit_ratio manquant")



def _candidate_output_dirs(raw_value: str | None) -> list[Path]:
    script_dir = Path(__file__).resolve().parent
    raw = (raw_value or "").strip()
    if not raw:
        return []
    requested = Path(raw).expanduser()
    candidates = [requested]
    if not requested.is_absolute():
        candidates.append(script_dir / requested)
        candidates.append(Path(tempfile.gettempdir()) / requested)
    return candidates



def resolve_output_dir(raw_value: str | None) -> Path | None:
    candidates = _candidate_output_dirs(raw_value)
    last_error: Exception | None = None
    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            probe = candidate / ".write_test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            if candidate != candidates[0]:
                print(f"[INFO] output-dir non inscriptible, fallback vers: {candidate}")
            return candidate
        except OSError as exc:
            last_error = exc
            continue
    if raw_value:
        print(f"[WARN] impossible d'écrire les sorties de test ({last_error}). Désactivation des fichiers de sortie.")
    return None



def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Exécute une batterie de smoke tests One Piece contre l'API Manga News.")
    parser.add_argument("--base-url", default=os.getenv("BASE_URL", "http://localhost:8017"), help="Base URL de l'API, par défaut http://localhost:8017")
    parser.add_argument("--token", default=os.getenv("API_TOKEN") or os.getenv("TOKEN"), help="Bearer token facultatif pour les endpoints publics")
    parser.add_argument("--admin-token", default=os.getenv("ADMIN_TOKEN") or os.getenv("TOKEN"), help="Bearer token facultatif pour les endpoints admin")
    parser.add_argument("--timeout", type=float, default=30.0, help="Timeout HTTP en secondes")
    parser.add_argument("--output-dir", default=os.getenv("API_TEST_OUTPUT_DIR", "api_test_outputs"), help="Dossier où écrire les réponses JSON. Le script bascule automatiquement vers un fallback writable si nécessaire.")
    return parser.parse_args()



def main() -> int:
    global runner
    args = parse_args()
    output_dir = resolve_output_dir(args.output_dir)
    runner = ApiRunner(base_url=args.base_url, token=args.token, admin_token=args.admin_token, timeout=args.timeout, output_dir=output_dir)

    runner.run("health", "GET", "/health", validator=validate_ok("health", ["ok"], True), expect_cache_headers=False)
    runner.run("search volume", "GET", "/search", params={"q": "one piece tome 91", "kind": "volume", "mode": "all", "limit": 10}, validator=validate_ok("search volume", ["data", 0, "volume_slug"], VOLUME_SLUG))
    runner.run("resolve volume", "GET", "/search/resolve", params={"q": "one piece tome 91", "kind": "volume", "limit": 10}, validator=validate_ok("resolve volume", ["data", "best", "volume_slug"], VOLUME_SLUG))
    runner.run("lookup volume", "GET", "/lookup/volume", params={"series": "One Piece", "number": "91", "limit": 10}, validator=validate_lookup)
    runner.run("volume", "GET", f"/volume/{VOLUME_SERIES_SLUG}/{VOLUME_SLUG}", validator=validate_volume)
    runner.run("volume by number", "GET", f"/volume/{SERIES_SLUG}/number/91", validator=validate_volume)
    runner.run("volume by url", "GET", "/volume/by-url", params={"url": VOLUME_URL}, validator=validate_volume)
    runner.run("news volume", "GET", f"/news/volume/{VOLUME_SERIES_SLUG}/{VOLUME_SLUG}", params={"limit": 10}, validator=validate_ok("news volume", ["ok"], True))
    runner.run("news volume by url", "GET", "/news/volume/by-url", params={"url": VOLUME_URL, "limit": 10}, validator=validate_ok("news volume by url", ["ok"], True))
    runner.run("search series", "GET", "/search", params={"q": "one piece", "kind": "series", "mode": "all", "limit": 10}, validator=validate_ok("search series", ["ok"], True))
    runner.run("resolve series", "GET", "/search/resolve", params={"q": "one piece", "kind": "series", "limit": 10}, validator=validate_ok("resolve series", ["data", "best", "slug"], SERIES_SLUG))
    runner.run("series", "GET", f"/series/{SERIES_SLUG}", validator=validate_series)
    runner.run("series by url", "GET", "/series/by-url", params={"url": SERIES_URL}, validator=validate_ok("series by url", ["data", "title"], "One Piece"))
    runner.run("series related", "GET", f"/series/{SERIES_SLUG}/related", validator=validate_ok("series related", ["ok"], True))
    runner.run("series related by url", "GET", "/series/by-url/related", params={"url": SERIES_URL}, validator=validate_ok("series related by url", ["ok"], True))
    runner.run("series editions", "GET", f"/series/{SERIES_SLUG}/editions", params={"edition": "all"}, validator=validate_ok("series editions", ["ok"], True))
    runner.run("series editions by url", "GET", "/series/by-url/editions", params={"url": SERIES_URL, "edition": "all"}, validator=validate_ok("series editions by url", ["ok"], True))
    runner.run("news global", "GET", "/news/global", params={"limit": 10}, validator=validate_ok("news global", ["ok"], True))
    runner.run("news series", "GET", f"/news/series/{SERIES_SLUG}", params={"limit": 10}, validator=validate_ok("news series", ["ok"], True))
    runner.run("planning", "GET", "/planning", params={"section": "manga-vf", "q": "one piece", "sort": "date_desc", "limit": 10}, validator=validate_ok("planning", ["ok"], True))
    runner.run("admin cache stats", "GET", "/admin/cache/stats", validator=validate_ok("admin cache stats", ["ok"], True), admin=True)
    runner.run("admin metrics", "GET", "/admin/metrics", validator=validate_metrics, admin=True)
    runner.run("admin invalidate series", "POST", "/admin/cache/invalidate", json_body={"resource_url": SERIES_URL}, validator=validate_ok("admin invalidate series", ["ok"], True), expect_cache_headers=False, admin=True)
    runner.run("admin invalidate volume", "POST", "/admin/cache/invalidate", json_body={"resource_url": VOLUME_URL}, validator=validate_ok("admin invalidate volume", ["ok"], True), expect_cache_headers=False, admin=True)

    if runner.etag:
        runner.run("etag 304 series", "GET", f"/series/{SERIES_SLUG}", if_none_match=runner.etag, expect_status=304, validator=validate_304, expect_cache_headers=False)
    else:
        runner.failures.append("etag 304 series: ETag non récupéré sur /series")
        print("[FAIL] etag 304 series: ETag non récupéré sur /series")

    print()
    print(f"Succès: {runner.passes}")
    print(f"Échecs: {len(runner.failures)}")
    if output_dir is not None:
        print(f"Sorties JSON: {output_dir}")
    if runner.failures:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
