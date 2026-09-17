"""Capture ?page=auto mobile screenshot and probe 2-column layout."""

from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / ".cursor-screenshots"
OUT_DIR.mkdir(parents=True, exist_ok=True)
FULL = OUT_DIR / "auto-page-mobile-390.png"
VIEW = OUT_DIR / "auto-page-viewport-390.png"

LAYOUT_JS = """
() => {
  const root = document.querySelector('.st-key-auto_page_columns_6n36s5');
  if (!root) return { error: 'missing auto_page_columns root' };
  const hbs = root.querySelectorAll('[data-testid="stHorizontalBlock"]');
  const results = [];
  hbs.forEach((hb, i) => {
    const cols = Array.from(hb.querySelectorAll(':scope > [data-testid="column"]'));
    const rects = cols.map((c) => {
      const r = c.getBoundingClientRect();
      return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) };
    });
    results.push({ index: i, colCount: cols.length, rects });
  });
  const main = results[0];
  let sideBySide = false;
  if (main && main.rects.length >= 2) {
    const [a, b] = main.rects;
    sideBySide = Math.abs(a.y - b.y) < 40 && a.x < b.x && a.w < 320 && b.w < 320;
  }
  return { sideBySide, blocks: results };
}
"""


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
        page.goto("http://127.0.0.1:8501/?page=auto", wait_until="networkidle", timeout=120_000)
        page.wait_for_selector("text=구매 방식", timeout=60_000)
        page.wait_for_timeout(8000)
        page.locator(".st-key-auto_stats_section_6n36s5").scroll_into_view_if_needed()
        page.wait_for_timeout(500)
        info = page.evaluate(LAYOUT_JS)
        page.screenshot(path=str(FULL), full_page=True)
        page.screenshot(path=str(VIEW), full_page=False)
        browser.close()
    print("layout_probe:", info)
    print("full:", FULL)
    print("viewport:", VIEW)


if __name__ == "__main__":
    main()
