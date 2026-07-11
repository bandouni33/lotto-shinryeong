import json

import streamlit.components.v1 as components

EXTRACT_BUTTON_KEYWORD = "번호 추출하기"
HAPTIC_DURATION_MS = 50
MAX_ATTACH_RETRIES = 15
RETRY_INTERVAL_MS = 400


def inject_mobile_scripts(button_keyword: str = EXTRACT_BUTTON_KEYWORD) -> None:
    """모바일 뷰포트 + 진동 브릿지 (단일 iframe, MutationObserver 미사용)."""
    keyword = json.dumps(button_keyword)
    duration = HAPTIC_DURATION_MS
    max_retries = MAX_ATTACH_RETRIES
    retry_ms = RETRY_INTERVAL_MS

    components.html(
        f"""
        <script>
        (function () {{
            const KEYWORD = {keyword};
            const DURATION = {duration};
            const MAX_RETRIES = {max_retries};
            const RETRY_MS = {retry_ms};

            function getParentDoc() {{
                try {{
                    return window.parent && window.parent.document;
                }} catch (err) {{
                    return null;
                }}
            }}

            function ensureViewport(doc) {{
                try {{
                    if (!doc || doc.querySelector('meta[name="viewport"]')) return;
                    const meta = doc.createElement("meta");
                    meta.name = "viewport";
                    meta.content = "width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover";
                    doc.head.appendChild(meta);
                }} catch (err) {{
                    /* ignore */
                }}
            }}

            function vibrate() {{
                try {{
                    const nav = window.parent.navigator || navigator;
                    if (nav && typeof nav.vibrate === "function") {{
                        nav.vibrate(DURATION);
                    }}
                }} catch (err) {{
                    /* ignore */
                }}
            }}

            function attachHaptic(doc) {{
                if (!doc) return false;
                let attached = false;

                doc.querySelectorAll("button").forEach((btn) => {{
                    const text = (btn.innerText || btn.textContent || "").trim();
                    if (!text.includes(KEYWORD) || btn.dataset.hapticBound === "1") {{
                        return;
                    }}
                    btn.dataset.hapticBound = "1";
                    btn.addEventListener("touchstart", vibrate, {{ passive: true }});
                    btn.addEventListener("click", vibrate);
                    attached = true;
                }});

                return attached;
            }}

            function boot() {{
                const doc = getParentDoc();
                ensureViewport(doc);

                let tries = 0;
                const timer = window.setInterval(() => {{
                    tries += 1;
                    attachHaptic(getParentDoc());
                    if (tries >= MAX_RETRIES) {{
                        window.clearInterval(timer);
                    }}
                }}, RETRY_MS);

                attachHaptic(doc);
            }}

            boot();
        }})();
        </script>
        """,
        height=0,
    )


# 하위 호환 alias
def inject_haptic_bridge(button_keyword: str = EXTRACT_BUTTON_KEYWORD) -> None:
    inject_mobile_scripts(button_keyword)


def inject_mobile_viewport() -> None:
    """deprecated: inject_mobile_scripts()가 뷰포트까지 처리함."""
    inject_mobile_scripts()
