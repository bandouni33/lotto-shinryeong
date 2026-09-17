"""Probe auto page DOM keys and gap."""
from playwright.sync_api import sync_playwright


def main() -> None:
    with sync_playwright() as p:
        page = p.chromium.launch(headless=True).new_page(
            viewport={"width": 390, "height": 844}
        )
        page.goto("http://127.0.0.1:8501/?page=auto", wait_until="networkidle", timeout=120_000)
        page.wait_for_selector("text=구매 확정", timeout=60_000)
        page.wait_for_timeout(8000)
        info = page.evaluate(
            """
() => {
  const keys = [];
  document.querySelectorAll('[class*="st-key-auto"]').forEach((el) => {
    el.className.split(/\\s+/).forEach((c) => {
      if (c.startsWith('st-key-auto')) keys.push(c);
    });
  });
  const uniq = [...new Set(keys)].sort();
  const hist = document.querySelector('.st-key-auto_purchase_history_zone_6n36s5');
  const stats = document.querySelector('.st-key-auto_stats_section_6n36s5');
  const visual = document.querySelector('.st-key-auto_visual_col_6n36s5');
  const rect = (el) => {
    if (!el) return null;
    const b = el.getBoundingClientRect();
    return { top: Math.round(b.top), bottom: Math.round(b.bottom), h: Math.round(b.height), w: Math.round(b.width) };
  };
  return {
    keys: uniq,
    bodyHasStatsText: document.body.innerText.includes('회차별'),
    hist: rect(hist),
    stats: rect(stats),
    visual: rect(visual),
    gap: hist && stats ? Math.round(stats.getBoundingClientRect().top - hist.getBoundingClientRect().bottom) : null,
  };
}
"""
        )
        print(info)


if __name__ == "__main__":
    main()
