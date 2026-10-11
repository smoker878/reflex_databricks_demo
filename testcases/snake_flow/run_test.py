import os
import sys
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
    output_dir = Path(os.getenv("OUTPUT_DIR", "testcases/snake_flow/output"))
    output_dir.mkdir(parents=True, exist_ok=True)

    headless = env_bool("HEADLESS", True)
    slow_mo = int(os.getenv("PW_SLOWMO_MS", "0"))
    timeout_ms = int(os.getenv("PW_TIMEOUT_MS", "30000"))

    # Seeded users: alice (id=1) and bob (id=2), password password123.
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, slow_mo=slow_mo)
        try:
            ctx_a = browser.new_context(viewport={"width": 1280, "height": 900})
            ctx_b = browser.new_context(viewport={"width": 1280, "height": 900})
            page_a = ctx_a.new_page()
            page_b = ctx_b.new_page()
            page_a.set_default_timeout(timeout_ms)
            page_b.set_default_timeout(timeout_ms)

            login(page_a, base_url, "alice", "password123")
            page_a.goto(base_url + "/dm/2", wait_until="domcontentloaded")
            page_a.get_by_role("heading", name="與 bob 的對話").wait_for()

            login(page_b, base_url, "bob", "password123")
            page_b.goto(base_url + "/dm/1", wait_until="domcontentloaded")
            page_b.get_by_role("heading", name="與 alice 的對話").wait_for()

            # alice invites bob to a snake battle from the chat composer.
            page_a.get_by_role("button", name="邀請遊戲").click()
            page_a.get_by_role("menuitem", name="貪食蛇（雙人對戰）").click()

            # bob receives the invitation dialog (on any page) and accepts.
            page_b.get_by_text("遊戲邀請").wait_for(timeout=15000)
            page_b.get_by_role("button", name="接受").click()

            # Both players are redirected into the battle room.
            page_a.get_by_role("heading", name="貪食蛇：bob").wait_for(timeout=15000)
            page_b.get_by_role("heading", name="貪食蛇：alice").wait_for(timeout=15000)

            board_a = page_a.locator("#snake-board")
            board_b = page_b.locator("#snake-board")
            board_a.wait_for(timeout=15000)
            board_b.wait_for(timeout=15000)

            # Wait until the countdown ends and the battle is live.
            page_a.get_by_text("對戰中").wait_for(timeout=15000)
            page_a.screenshot(path=str(output_dir / "snake_alice.png"), full_page=True)

            # alice immediately steers into the top wall, so bob should win.
            page_a.bring_to_front()
            board_a.click()
            for _ in range(6):
                page_a.keyboard.press("ArrowUp")
                page_a.wait_for_timeout(60)

            winner_a = page_a.locator("#snake-winner")
            winner_a.wait_for(timeout=15000)
            result_a = winner_a.inner_text().strip()

            # bob must observe the same outcome via the shared game state.
            winner_b = page_b.locator("#snake-winner")
            winner_b.wait_for(timeout=15000)
            result_b = winner_b.inner_text().strip()
            print(f"[result] alice sees: {result_a!r} / bob sees: {result_b!r}")

            assert "bob 獲勝" in result_a, f"expected bob to win, alice saw: {result_a}"
            assert result_a == result_b, "clients saw different results"

            page_a.screenshot(path=str(output_dir / "snake_over_a.png"), full_page=True)
            page_b.screenshot(path=str(output_dir / "snake_over_b.png"), full_page=True)

            ctx_a.close()
            ctx_b.close()
            return 0
        except Exception:
            try:
                for context in browser.contexts:
                    for page in context.pages:
                        page.screenshot(
                            path=str(output_dir / "failure.png"), full_page=True
                        )
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
        print(f"snake_flow failed: {exc}", file=sys.stderr)
        raise
