from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from core.errors import ClipForgeError


@dataclass(frozen=True, slots=True)
class CookieSelection:
    platform: str
    path: Path
    source: Path
    valid_count: int
    expired_count: int
    converted: bool = False


class CookieManager:
    """Finds, validates and converts platform cookies for yt-dlp."""

    PLATFORM_DOMAINS: dict[str, tuple[str, ...]] = {
        "youtube": ("youtube.com", "youtu.be", "googlevideo.com"),
        "instagram": ("instagram.com",),
        "tiktok": ("tiktok.com",),
        "twitter": ("x.com", "twitter.com"),
    }

    AUTH_COOKIE_NAMES: dict[str, tuple[str, ...]] = {
        "youtube": ("SAPISID", "SID", "LOGIN_INFO", "__Secure-1PSID", "__Secure-3PSID"),
        "instagram": ("sessionid", "ds_user_id", "csrftoken"),
        "tiktok": ("sessionid", "sid_tt", "ttwid"),
        "twitter": ("auth_token", "ct0", "twid"),
    }

    def __init__(self, *, root: str | Path | None = None, cookie_dir: str | Path | None = None) -> None:
        self.root = Path(root).resolve() if root else Path(__file__).resolve().parents[1]
        self.cookie_dir = Path(cookie_dir).resolve() if cookie_dir else self.root / "cookies"
        self.legacy_dirs = (self.root, self.root / "downloaders")

    def get_cookiefile(self, url: str) -> CookieSelection | None:
        platform = self.detect_platform(url)
        for candidate in self._candidate_files(platform):
            if not candidate.is_file():
                continue
            if self._looks_like_netscape(candidate):
                selection = self._validate_netscape(candidate, platform)
                if selection.valid_count:
                    return selection
                continue
            if candidate.suffix.lower() == ".json":
                converted = self._convert_json(candidate, platform)
                selection = self._validate_netscape(converted, platform)
                if selection.valid_count:
                    return CookieSelection(
                        platform=platform,
                        path=selection.path,
                        source=candidate,
                        valid_count=selection.valid_count,
                        expired_count=selection.expired_count,
                        converted=True,
                    )
        return None

    def require_cookiefile(self, url: str) -> Path:
        selection = self.get_cookiefile(url)
        if selection is None:
            platform = self.detect_platform(url)
            raise ClipForgeError(
                f"Nenhum cookie valido foi encontrado para {platform}. "
                f"Exporte cookies em cookies/{platform}.txt ou cookies/{platform}.json e tente novamente."
            )
        return selection.path

    def detect_platform(self, url: str) -> str:
        host = (urlparse(url).hostname or "").lower().removeprefix("www.")
        for platform, domains in self.PLATFORM_DOMAINS.items():
            if any(host == domain or host.endswith(f".{domain}") for domain in domains):
                return platform
        return "generic"

    def _candidate_files(self, platform: str) -> list[Path]:
        names = [platform] if platform != "generic" else []
        if platform == "twitter":
            names.extend(["x"])
        names.append("cookies")

        candidates: list[Path] = []
        search_dirs = (self.cookie_dir, *self.legacy_dirs)
        for directory in search_dirs:
            for name in names:
                candidates.append(directory / f"{name}.txt")
                candidates.append(directory / f"{name}.json")
        return self._unique_paths(candidates)

    def _convert_json(self, source: Path, platform: str) -> Path:
        with source.open("r", encoding="utf-8-sig") as handle:
            payload = json.load(handle)
        cookies = payload.get("cookies", payload) if isinstance(payload, dict) else payload
        if not isinstance(cookies, list):
            raise ClipForgeError(f"Arquivo de cookies JSON invalido: {source}")

        rows = ["# Netscape HTTP Cookie File", "# Generated automatically by CookieManager."]
        valid_count = 0
        expired_count = 0
        now = int(time.time())
        for cookie in cookies:
            if not isinstance(cookie, dict):
                continue
            domain = str(cookie.get("domain") or "").strip()
            name = str(cookie.get("name") or "").strip()
            value = str(cookie.get("value") or "")
            if not domain or not name:
                continue
            if not self._domain_matches_platform(domain, platform):
                continue
            expires = self._cookie_expiry(cookie)
            if expires and expires < now:
                expired_count += 1
                continue
            valid_count += 1
            include_subdomains = "TRUE" if domain.startswith(".") else "FALSE"
            path = str(cookie.get("path") or "/")
            secure = "TRUE" if bool(cookie.get("secure", True)) else "FALSE"
            rows.append("\t".join([domain, include_subdomains, path, secure, str(expires), name, value]))

        if valid_count == 0 and expired_count:
            raise ClipForgeError(
                f"Todos os cookies de {platform} estao expirados. Exporte uma nova sessao e tente novamente."
            )
        if valid_count == 0:
            raise ClipForgeError(f"Nenhum cookie de {platform} foi encontrado em {source}.")

        self.cookie_dir.mkdir(parents=True, exist_ok=True)
        target = self.cookie_dir / f"{platform}.txt"
        target.write_text("\n".join(rows) + "\n", encoding="utf-8")
        return target

    def _validate_netscape(self, source: Path, platform: str) -> CookieSelection:
        valid_count = 0
        expired_count = 0
        now = int(time.time())
        for raw_line in source.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            parts = raw_line.split("\t")
            if len(parts) < 7:
                continue
            domain, _, _, _, expires_raw, name, _ = parts[:7]
            if not self._domain_matches_platform(domain, platform):
                continue
            try:
                expires = int(float(expires_raw or "0"))
            except ValueError:
                expires = 0
            if expires and expires < now:
                expired_count += 1
                continue
            valid_count += 1

        if valid_count == 0 and expired_count:
            raise ClipForgeError(
                f"Todos os cookies de {platform} estao expirados. Exporte uma nova sessao e tente novamente."
            )
        return CookieSelection(platform, source, source, valid_count, expired_count)

    def _domain_matches_platform(self, domain: str, platform: str) -> bool:
        if platform == "generic":
            return True
        normalized = domain.lower().lstrip(".")
        return any(
            normalized == expected or normalized.endswith(f".{expected}")
            for expected in self.PLATFORM_DOMAINS[platform]
        )

    @staticmethod
    def _cookie_expiry(cookie: dict) -> int:
        for key in ("expirationDate", "expires", "expiry", "expiration"):
            value = cookie.get(key)
            if value in (None, ""):
                continue
            try:
                return max(0, int(float(value)))
            except (TypeError, ValueError):
                continue
        return 0

    @staticmethod
    def _looks_like_netscape(path: Path) -> bool:
        with path.open("r", encoding="utf-8-sig", errors="replace") as handle:
            for _ in range(5):
                line = handle.readline()
                if not line:
                    return False
                stripped = line.strip()
                if not stripped:
                    continue
                return stripped.startswith("# Netscape") or "\t" in stripped
        return False

    @staticmethod
    def _unique_paths(paths: list[Path]) -> list[Path]:
        seen: set[Path] = set()
        unique: list[Path] = []
        for path in paths:
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            unique.append(path)
        return unique
