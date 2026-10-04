"""서버측 자원 샘플러 — Streamlit 프로세스의 RSS(작업집합)와 CPU를 주기적으로 기록한다.

왜 필요한가(2026-10-04 지시: "각 단계에서 서버 메모리(RSS) 총사용량, CPU 사용률 기록"):
  이 저장소의 부하테스트(scripts/load_test_concurrency.py)는 **클라이언트**가 본 지연과
  이 PC의 여유 RAM만 잰다 — 정작 알고 싶은 "서버 프로세스가 세션 하나에 얼마를 더 쓰는가"는
  못 잰다. psutil이 이 venv에 없으므로 Win32 API를 ctypes로 직접 부른다.

무엇을 재는가:
  * rss_mb      : 그 PID의 WorkingSetSize(작업집합 = 실제 상주 메모리)
  * py_rss_mb   : 이름이 python.exe인 프로세스 전체의 RSS 합(Streamlit이 자식을 띄울 때 대비)
  * proc_cpu    : 그 프로세스의 (커널+유저) 누적 CPU 시간 증가분 → 샘플 구간 CPU%
                  (코어 1개 기준과 이 PC 전체 기준 둘 다 찍는다)
  * sys_cpu     : 시스템 전체 CPU 사용률(다른 프로세스가 코어를 먹는지 구분용 —
                  같은 PC에서 브라우저 부하를 함께 돌리면 이 값이 높아진다)
  * free_mb     : 이 PC 여유 물리 메모리

사용:
  venv312\\Scripts\\python.exe -u -X utf8 scratch\\monitor_streamlit_resources.py --port 8599 --out scratch\\rss_samples.csv
  (포트로 PID를 찾는다. --pid 로 직접 줄 수도 있다.)
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wt
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_VM_READ = 0x0010


class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
    _fields_ = [
        ("cb", wt.DWORD),
        ("PageFaultCount", wt.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
        ("PrivateUsage", ctypes.c_size_t),
    ]


class FILETIME(ctypes.Structure):
    _fields_ = [("dwLowDateTime", wt.DWORD), ("dwHighDateTime", wt.DWORD)]

    def seconds(self) -> float:
        return (self.dwHighDateTime << 32 | self.dwLowDateTime) / 1e7


def pid_on_port(port: int) -> int | None:
    """netstat으로 그 포트를 LISTENING 중인 PID를 찾는다(psutil 없이)."""
    try:
        out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True,
                             encoding="utf-8", errors="replace").stdout
    except Exception:
        return None
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[0].upper().startswith("TCP") and \
                parts[1].endswith(f":{port}") and parts[3].upper() == "LISTENING":
            try:
                return int(parts[4])
            except ValueError:
                continue
    return None


def open_proc(pid: int):
    return ctypes.windll.kernel32.OpenProcess(
        PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_VM_READ, False, pid)


def rss_mb(pid: int) -> float | None:
    handle = open_proc(pid)
    if not handle:
        return None
    try:
        counters = PROCESS_MEMORY_COUNTERS_EX()
        counters.cb = ctypes.sizeof(counters)
        ok = ctypes.windll.psapi.GetProcessMemoryInfo(
            handle, ctypes.byref(counters), ctypes.sizeof(counters))
        return counters.WorkingSetSize / (1024 * 1024) if ok else None
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def cpu_seconds(pid: int) -> float | None:
    handle = open_proc(pid)
    if not handle:
        return None
    try:
        creation, exit_, kernel, user = FILETIME(), FILETIME(), FILETIME(), FILETIME()
        ok = ctypes.windll.kernel32.GetProcessTimes(
            handle, ctypes.byref(creation), ctypes.byref(exit_),
            ctypes.byref(kernel), ctypes.byref(user))
        return kernel.seconds() + user.seconds() if ok else None
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def filetime_now() -> float:
    ft = FILETIME()
    ctypes.windll.kernel32.GetSystemTimeAsFileTime(ctypes.byref(ft))
    return ft.seconds()


def cpu_totals() -> tuple[float, float] | None:
    """(idle, kernel+user) 누적 시간. 시스템 전체 CPU%를 위해 쓴다."""
    idle, kernel, user = FILETIME(), FILETIME(), FILETIME()
    ok = ctypes.windll.kernel32.GetSystemTimes(
        ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user))
    if not ok:
        return None
    return idle.seconds(), kernel.seconds() + user.seconds()


def mem_status_mb() -> tuple[float, float] | None:
    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", wt.DWORD), ("dwMemoryLoad", wt.DWORD),
            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    st = MEMORYSTATUSEX()
    st.dwLength = ctypes.sizeof(st)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
        return None
    return st.ullTotalPhys / (1024 * 1024), st.ullAvailPhys / (1024 * 1024)


def python_total_mb() -> float:
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-Process python -ErrorAction SilentlyContinue | "
             "Measure-Object -Property WorkingSet64 -Sum).Sum"],
            capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.strip()
        return round(float(out) / (1024 * 1024), 1) if out and out.replace(".", "").isdigit() else 0.0
    except Exception:
        return 0.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8599, help="이 포트의 LISTENING PID를 대상으로")
    ap.add_argument("--pid", type=int, default=None, help="PID를 직접 지정")
    ap.add_argument("--interval", type=float, default=2.0, help="샘플 주기(초)")
    ap.add_argument("--wait", type=float, default=120, help="PID를 못 찾을 때 기다리는 상한(초)")
    ap.add_argument("--duration", type=float, default=0, help="0이면 Ctrl+C까지 계속")
    ap.add_argument("--out", default=str(ROOT / "scratch" / "rss_samples.csv"))
    args = ap.parse_args()

    pid = args.pid
    if not pid:
        # 서버가 부팅(=데이터 시드) 중일 수 있다 — 포기하지 않고 상한까지 기다린다.
        import time as _t
        deadline = _t.time() + args.wait
        while not pid and _t.time() < deadline:
            pid = pid_on_port(args.port)
            if not pid:
                _t.sleep(2)
        if not pid:
            print(f"실패: 포트 {args.port}에 LISTENING 중인 프로세스가 없다", flush=True)
            return 1
    print(f"[monitor] 대상 PID {pid} (포트 {args.port}) · 주기 {args.interval}s", flush=True)

    header = "t,elapsed_s,rss_mb,py_rss_mb,proc_cpu_pct,poc_cpu_total,sys_cpu_pct,free_mb"
    Path(args.out).write_text(header + "\n", encoding="utf-8")
    print(header, flush=True)

    t0 = time.time()
    prev_cpu = cpu_seconds(pid) or 0.0
    prev_totals = cpu_totals()
    cores = 0
    try:
        cores = int(subprocess.run(["powershell", "-NoProfile", "-Command",
                                    "(Get-CimInstance Win32_ComputerSystem).NumberOfLogicalProcessors"],
                                   capture_output=True, text=True).stdout.strip())
    except Exception:
        cores = 1
    cores = cores or 1

    try:
        while True:
            time.sleep(args.interval)
            now = time.time()
            elapsed = now - t0
            cur_cpu = cpu_seconds(pid)
            totals = cpu_totals()
            proc_pct = sys_pct = 0.0
            if cur_cpu is not None:
                proc_pct = (cur_cpu - prev_cpu) / args.interval / cores * 100.0
                prev_cpu = cur_cpu
            if prev_totals and totals:
                d_idle = totals[0] - prev_totals[0]
                d_busy = totals[1] - prev_totals[1]
                sys_pct = (1 - d_idle / d_busy) * 100.0 if d_busy > 0 else 0.0
                prev_totals = totals
            rss = rss_mb(pid)
            mem = mem_status_mb()
            # python 총합은 PowerShell을 띄우므로 5번에 한 번만(샘플링 자체가 부하가 되면 안 된다)
            py_total = python_total_mb() if int(elapsed / args.interval) % 5 == 0 else None
            row = (f"{datetime.now():%H:%M:%S},{elapsed:.1f},"
                   f"{'' if rss is None else round(rss, 1)},"
                   f"{'' if py_total is None else py_total},"
                   f"{proc_pct:.1f},{'' if cur_cpu is None else round(cur_cpu, 1)},"
                   f"{sys_pct:.1f},{'' if mem is None else round(mem[1])}")
            with open(args.out, "a", encoding="utf-8") as fh:
                fh.write(row + "\n")
            print(row, flush=True)
            if args.duration and elapsed >= args.duration:
                break
    except KeyboardInterrupt:
        print("[monitor] 중단", flush=True)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
