import os
import sys
import uuid
from pathlib import Path

from playwright.sync_api import sync_playwright


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def login(page, base_url: str, username: str, password: str) -> None:
    page.goto(base_url + "/login", wait_until="domcontentloaded")
    page.get_by_role("heading", name="Login into your Account").wait_for()
    page.locator("#username").fill(username)
    page.locator("#password").fill(password)
    page.get_by_role("button", name="Sign in").click()
    page.get_by_role("heading", name="好友").wait_for()


def main() -> int:
    base_url = os.getenv("BASE_URL", "http://127.0.0.1:3000").rstrip("/")
    output_dir = Path(os.getenv("OUTPUT_DIR", "testcases/dm_flow/output"))
    output_dir.mkdir(parents=True, exist_ok=True)

    headless = env_bool("HEADLESS", True)
    slow_mo = int(os.getenv("PW_SLOWMO_MS", "0"))
    timeout_ms = int(os.getenv("PW_TIMEOUT_MS", "30000"))

    # Seeded users: alice (id=1) and bob (id=2), password password123.
    message = f"hello-{uuid.uuid4().hex[:8]}"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, slow_mo=slow_mo)
        try:
            ctx_a = browser.new_context(viewport={"width": 1280, "height": 900})
            ctx_b = browser.new_context(viewport={"width": 1280, "height": 900})
            page_a = ctx_a.new_page()
            page_b = ctx_b.new_page()
            page_a.set_default_timeout(timeout_ms)
            page_b.set_default_timeout(timeout_ms)

            # alice chats with bob (/dm/2); bob chats with alice (/dm/1).
            login(page_a, base_url, "alice", "password123")
            page_a.goto(base_url + "/dm/2", wait_until="domcontentloaded")
            page_a.get_by_role("heading", name="與 bob 的對話").wait_for()

            login(page_b, base_url, "bob", "password123")
            page_b.goto(base_url + "/dm/1", wait_until="domcontentloaded")
            page_b.get_by_role("heading", name="與 alice 的對話").wait_for()

            # alice types: bob should see the typing indicator (broadcast).
            composer_a = page_a.get_by_placeholder("輸入訊息…")
            composer_a.click()
            composer_a.type(message, delay=60)
            page_b.get_by_text("對方正在輸入…").wait_for(timeout=10000)

            # alice sends: bob receives it in real time via SharedState broadcast.
            page_a.get_by_role("button", name="送出").click()
            messages_a = page_a.locator("#dm-messages")
            messages_b = page_b.locator("#dm-messages")
            messages_b.get_by_text(message).wait_for(timeout=10000)
            messages_a.get_by_text(message).wait_for(timeout=10000)

            # Alignment: own messages on the right, the peer's on the left.
            own_box = messages_a.get_by_text(message).bounding_box()
            peer_box = messages_b.get_by_text(message).bounding_box()
            assert own_box and own_box["x"] > 640, f"own message not right-aligned: {own_box}"
            assert peer_box and peer_box["x"] < 640, f"peer message not left-aligned: {peer_box}"

            page_b.screenshot(path=str(output_dir / "dm_bob.png"), full_page=True)

            # History persists across reload (loaded from SQLite on join).
            page_b.reload(wait_until="domcontentloaded")
            page_b.get_by_role("heading", name="與 alice 的對話").wait_for()
            page_b.get_by_text(message).wait_for(timeout=10000)

            ctx_a.close()
            ctx_b.close()
            return 0
        except Exception:
            try:
                for page in browser.contexts[0].pages if browser.contexts else []:
                    page.screenshot(path=str(output_dir / "failure.png"), full_page=True)
            except Exception:
                pass
            raise
        finally:
            browser.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise
    except Exception as exc:
        print(f"dm_flow failed: {exc}", file=sys.stderr)
        raise
