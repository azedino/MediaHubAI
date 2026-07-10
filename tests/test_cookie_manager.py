import json
import time

from downloaders.cookies import CookieManager


def test_cookie_manager_converts_platform_json_to_netscape(tmp_path):
    root = tmp_path
    cookie_dir = root / "cookies"
    cookie_dir.mkdir()
    expiry = int(time.time()) + 3600
    (cookie_dir / "twitter.json").write_text(
        json.dumps(
            [
                {
                    "domain": ".x.com",
                    "name": "auth_token",
                    "value": "token",
                    "path": "/",
                    "secure": True,
                    "expirationDate": expiry,
                }
            ]
        ),
        encoding="utf-8",
    )

    selection = CookieManager(root=root).get_cookiefile("https://x.com/example/status/1")

    assert selection is not None
    assert selection.converted is True
    assert selection.path == cookie_dir / "twitter.txt"
    assert "auth_token" in selection.path.read_text(encoding="utf-8")


def test_cookie_manager_accepts_netscape_file_with_json_extension(tmp_path):
    root = tmp_path
    expiry = int(time.time()) + 3600
    (root / "cookies.json").write_text(
        "\n".join(
            [
                "# Netscape HTTP Cookie File",
                f".x.com\tTRUE\t/\tTRUE\t{expiry}\tauth_token\ttoken",
            ]
        ),
        encoding="utf-8",
    )

    selection = CookieManager(root=root).get_cookiefile("https://x.com/example/status/1")

    assert selection is not None
    assert selection.path == root / "cookies.json"
    assert selection.valid_count == 1
