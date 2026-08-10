import streamlit.components.v1 as components

MIN_ZOOM = 1.0
MAX_ZOOM = 2.5


def inject_pinch_zoom() -> None:
    """두 손가락 핀치로 화면 전체를 확대/축소한다 (시력이 안 좋은 사용자를 위한 접근성 기능).

    네이티브 WebView의 확대 옵션(setBuiltInZoomControls)만으로는 실기기에서 핀치줌이
    잘 안 된다는 리포트가 있어, 웹 콘텐츠 쪽에 자체 구현으로 대체한다.

    구현 방식 메모(실기기에서 두 번 깨진 뒤 정리):
      - transform:scale(body)는 시도했다가 되돌렸다 — CSS 스펙상 조상에 transform이
        붙으면 그 안의 position:fixed 요소(업데이트 배너 등)의 기준이 뷰포트가 아니라
        그 조상으로 바뀌어버려서, 확대 시 화면이 엉뚱한 위치로 밀려 하얗게 보이는
        문제가 있었다.
      - 그래서 CSS zoom을 쓴다. zoom은 레이아웃을 다시 계산하는 방식이라 스크롤이
        자연스럽게 따라오고 fixed 요소도 깨지지 않는다. 다만 항상 왼쪽 위를 기준으로
        커지기 때문에(zoom-origin 같은 속성이 없다) 핀치한 지점이 정중앙에 고정되진
        않는다 — 대신 확실히 안전하게 동작한다.
    두 손가락 터치는 iframe(커스텀 컴포넌트) 밖 메인 문서에서만 감지된다.
    """
    components.html(
        """
        <script>
        (function () {
            const doc = window.parent.document;
            if (!doc || doc.__pinchZoomInit) return;
            doc.__pinchZoomInit = true;

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

            function applyZoom(z) {
                zoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, z));
                doc.body.style.zoom = zoom === 1 ? '' : zoom;
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
                    applyZoom(startZoom * (dist / startDistance));
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
