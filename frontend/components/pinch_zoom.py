import streamlit.components.v1 as components

MIN_ZOOM = 1.0
MAX_ZOOM = 2.5


def inject_pinch_zoom() -> None:
    """두 손가락 핀치로 화면 전체를 확대/축소한다 (시력이 안 좋은 사용자를 위한 접근성 기능).

    네이티브 WebView의 확대 옵션(setBuiltInZoomControls)만으로는 실기기에서 핀치줌이
    잘 안 된다는 리포트가 있어, 웹 콘텐츠 쪽에 자체 구현으로 대체한다.

    구현 방식 메모(실기기에서 문제 겪은 뒤 정리):
      - transform:scale(body)는 시도했다가 되돌렸다 — CSS 스펙상 조상에 transform이
        붙으면 그 안의 position:fixed 요소(업데이트 배너 등)의 기준이 뷰포트가 아니라
        그 조상으로 바뀌어버려서, 확대 시 화면이 엉뚱한 위치로 밀려 하얗게 보이는
        문제가 있었다.
      - 그래서 CSS zoom을 쓴다 — fixed 요소를 깨뜨리지 않는다. 다만 zoom은 항상
        왼쪽 위를 기준으로 다시 레이아웃을 계산하므로, 그대로 두면 핀치한 지점이
        아니라 좌상단이 고정된 것처럼 보인다. transform 없이 "핀치한 지점이 화면에서
        안 움직이는" 느낌을 내기 위해, zoom을 바꾼 직후 스크롤 위치를 계산해서
        보정한다 (핀치 지점의 문서상 논리 좌표가 화면의 같은 자리에 남도록).
    두 손가락 터치는 iframe(커스텀 컴포넌트) 밖 메인 문서에서만 감지된다.
    """
    components.html(
        """
        <script>
        (function () {
            const doc = window.parent.document;
            if (!doc || doc.__pinchZoomInit) return;
            doc.__pinchZoomInit = true;

            // 이 앱은 window/body가 아니라 [data-testid="stMain"] 내부 컨테이너가
            // 실제로 스크롤된다(.stApp는 overflow:hidden으로 감싸고 있음) — 스크롤
            // 보정은 이 요소를 대상으로 해야 한다. 못 찾으면 window로 폴백한다.
            function getScroller() {
                return doc.querySelector('[data-testid="stMain"]');
            }

            const MIN_ZOOM = %s;
            const MAX_ZOOM = %s;
            let zoom = 1;
            let startDistance = 0;
            let startZoom = 1;
            let lastTapAt = 0;

            function getDistance(touches) {
                const dx = touches[0].clientX - touches[1].clientX;
                const dy = touches[0].clientY - touches[1].clientY;
                return Math.sqrt(dx * dx + dy * dy);
            }

            function getMidpoint(touches) {
                return {
                    x: (touches[0].clientX + touches[1].clientX) / 2,
                    y: (touches[0].clientY + touches[1].clientY) / 2,
                };
            }

            function applyZoom(z, midX, midY) {
                const zoomOld = zoom;
                zoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, z));
                if (zoom === zoomOld) return;

                const scroller = getScroller();
                let scrollX0 = 0;
                let scrollY0 = 0;
                if (midX != null && midY != null && scroller) {
                    scrollX0 = scroller.scrollLeft || 0;
                    scrollY0 = scroller.scrollTop || 0;
                }

                doc.body.style.zoom = zoom === 1 ? '' : zoom;

                if (midX != null && midY != null && zoomOld > 0 && scroller) {
                    const ratio = zoom / zoomOld;
                    scroller.scrollLeft = (scrollX0 + midX) * ratio - midX;
                    scroller.scrollTop = (scrollY0 + midY) * ratio - midY;
                }
            }

            doc.addEventListener('touchstart', function (e) {
                if (e.touches.length === 2) {
                    startDistance = getDistance(e.touches);
                    startZoom = zoom;
                }
            }, { passive: true });

            doc.addEventListener('touchmove', function (e) {
                if (e.touches.length === 2 && startDistance > 0) {
                    e.preventDefault();
                    const dist = getDistance(e.touches);
                    const mid = getMidpoint(e.touches);
                    applyZoom(startZoom * (dist / startDistance), mid.x, mid.y);
                }
            }, { passive: false });

            doc.addEventListener('touchend', function (e) {
                if (e.touches.length > 0) return;
                startDistance = 0;
                const now = Date.now();
                if (now - lastTapAt < 300) {
                    applyZoom(1);
                    lastTapAt = 0;
                } else {
                    lastTapAt = now;
                }
            });
        })();
        </script>
        """
        % (MIN_ZOOM, MAX_ZOOM),
        height=0,
    )
