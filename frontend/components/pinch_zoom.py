import streamlit.components.v1 as components

MIN_ZOOM = 1.0
MAX_ZOOM = 2.5


def inject_pinch_zoom() -> None:
    """두 손가락 핀치로 화면 전체를 확대/축소한다 (시력이 안 좋은 사용자를 위한 접근성 기능).

    네이티브 WebView의 확대 옵션(setBuiltInZoomControls)만으로는 실기기에서 핀치줌이
    잘 안 된다는 리포트가 있어, 웹 콘텐츠 쪽에 자체 구현으로 대체한다.

    구현 방식 메모(실기기에서 여러 번 문제를 겪은 뒤 정리):
      1차 — CSS zoom: fixed 요소는 안 깨지지만 레이아웃을 다시 계산해서 텍스트가
        줄바꿈되며 움직였다. "사진처럼 그 자리에서 커지는" 느낌을 원해서 폐기.
      2차 — transform:scale(body): 시각적으로만 커져서 텍스트는 안 움직이지만,
        body 전체에 걸면 fixed 요소(업데이트 배너) 기준점이 깨지고 좌표 계산도
        어긋나 화면이 빈 공간(흰 화면)으로 밀려나는 문제가 있었다.
      3차 — transform:scale(stMain, 스크롤되는 요소 자체): 확대는 잘 되지만,
        "스크롤되는 요소 자기 자신"에 transform을 걸면 그 조상 입장에서 레이아웃
        크기가 그대로라 스크롤 가능 범위가 커진 콘텐츠만큼 안 늘어난다 — 화면
        범위 밖으로 확대된 부분을 스크롤해서 볼 수가 없었다.

      최종: 실제 스크롤은 [data-testid="stMain"]에서 일어나지만, transform은 그
      안쪽 자식인 [data-testid="stMainBlockContainer"](진짜 페이지 콘텐츠)에
      건다 — 스크롤 컨테이너 자신은 그대로 두고 "그 안의 콘텐츠"만 확대해야,
      브라우저가 확대된 콘텐츠의 실제 렌더링 크기만큼 스크롤 컨테이너의 스크롤
      가능 범위를 자동으로 늘려준다. transform-origin을 핀치 지점으로 잡아두면
      스크롤 보정을 따로 계산할 필요 없이 그 지점이 화면에서 자연히 고정된다.
    두 손가락 터치는 iframe(커스텀 컴포넌트) 밖 메인 문서에서만 감지된다.
    """
    components.html(
        """
        <script>
        (function () {
            const doc = window.parent.document;
            if (!doc || doc.__pinchZoomInit) return;
            doc.__pinchZoomInit = true;

            function getZoomTarget() {
                return doc.querySelector('[data-testid="stMainBlockContainer"]');
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

            function setToastVisible(visible) {
                const toast = doc.getElementById('update-toast-6n36s5');
                if (toast) toast.style.visibility = visible ? '' : 'hidden';
            }

            function applyZoom(z, clientX, clientY) {
                const target = getZoomTarget();
                if (!target) return;
                const zoomOld = zoom;
                zoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, z));
                if (zoom === zoomOld) return;

                if (clientX != null && clientY != null) {
                    const rect = target.getBoundingClientRect();
                    target.style.transformOrigin =
                        (clientX - rect.left) + 'px ' + (clientY - rect.top) + 'px';
                }
                target.style.transform = zoom === 1 ? '' : 'scale(' + zoom + ')';
                setToastVisible(zoom === 1);
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
