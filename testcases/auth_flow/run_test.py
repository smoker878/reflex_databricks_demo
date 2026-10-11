import os
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def main() -> int:
    base_url = os.getenv("BASE_URL", "http://127.0.0.1:3000").rstrip("/")
    output_dir = Path(os.getenv("OUTPUT_DIR", "testcases/auth_flow/output"))
    output_dir.mkdir(parents=True, exist_ok=True)

    headless = env_bool("HEADLESS", True)
    slow_mo = int(os.getenv("PW_SLOWMO_MS", "0"))
    timeout_ms = int(os.getenv("PW_TIMEOUT_MS", "30000"))

    username = f"tester{int(time.time())}"
    password = "password123"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, slow_mo=slow_mo)
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()
        page.set_default_timeout(timeout_ms)

        try:
            # Unauthenticated access to "/" redirects to /login.
            page.goto(base_url + "/", wait_until="domcontentloaded")
            page.get_by_role("heading", name="Login into your Account").wait_for()

            # Register a new account.
            page.goto(base_url + "/register", wait_until="domcontentloaded")
            page.locator("#username").fill(username)
            page.locator("#password").fill(password)
            page.locator("#confirm_password").fill(password)
            page.get_by_role("button", name="Sign up").click()
            page.get_by_text("Registration successful!").wait_for()

            # Redirected back to login; sign in.
            page.get_by_role("heading", name="Login into your Account").wait_for()
            page.locator("#username").fill(username)
            page.locator("#password").fill(password)
            page.get_by_role("button", name="Sign in").click()

            # Authenticated: the friends sidebar lists seeded contacts.
            page.get_by_role("heading", name="好友").wait_for()
            page.get_by_text("bob", exact=True).first.wait_for(timeout=15000)
            page.screenshot(path=str(output_dir / "lobby.png"), full_page=True)

            # Logout returns to the login page.
            page.get_by_role("button", name="登出").click()
            page.get_by_role("heading", name="Login into your Account").wait_for()

            return 0
        except Exception:
            try:
                page.screenshot(path=str(output_dir / "failure.png"), full_page=True)
            except Exception:
                pass
            raise
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise
    except Exception as exc:
        print(f"auth_flow failed: {exc}", file=sys.stderr)
        raise
