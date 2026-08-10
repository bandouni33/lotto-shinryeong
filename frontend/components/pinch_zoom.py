import streamlit.components.v1 as components

MIN_ZOOM = 1.0
MAX_ZOOM = 2.5


def inject_pinch_zoom() -> None:
    """두 손가락 핀치로 화면 전체를 확대/축소한다 (시력이 안 좋은 사용자를 위한 접근성 기능).

    네이티브 WebView의 확대 옵션(setBuiltInZoomControls)만으로는 실기기에서 핀치줌이
    잘 안 된다는 리포트가 있어, 웹 콘텐츠 쪽에 자체 구현으로 대체한다.
    CSS zoom은 레이아웃을 왼쪽 위 기준으로 다시 계산해서 화면이 아래로만 늘어나 보이는
    문제가 있었다 — transform:scale + 핀치 중심점을 transform-origin으로 써서, 손가락을
    댄 지점을 중심으로 커지도록(사진 앱 핀치줌과 비슷한 느낌으로) 바꿨다.
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

            function getMidpoint(touches) {
                return {
                    x: (touches[0].pageX + touches[1].pageX) / 2,
                    y: (touches[0].pageY + touches[1].pageY) / 2,
                };
            }

            function applyZoom(z, origin) {
                zoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, z));
                if (origin) {
                    doc.body.style.transformOrigin = origin.x + 'px ' + origin.y + 'px';
                }
                doc.body.style.transform = zoom === 1 ? '' : 'scale(' + zoom + ')';
            }

            doc.addEventListener('touchstart', function (e) {
                if (e.touches.length === 2) {
                    startDistance = getDistance(e.touches);
                    startZoom = zoom;
                    doc.body.style.transformOrigin =
                        getMidpoint(e.touches).x + 'px ' + getMidpoint(e.touches).y + 'px';
                }
            }, { passive: true });

            doc.addEventListener('touchmove', function (e) {
                if (e.touches.length === 2 && startDistance > 0) {
                    e.preventDefault();
                    const dist = getDistance(e.touches);
                    applyZoom(startZoom * (dist / startDistance), getMidpoint(e.touches));
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
