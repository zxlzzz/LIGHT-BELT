"""Monitor complete serial lines from two ESP32 commissioning nodes.

The ports are opened with DTR and RTS disabled so this tool does not
intentionally reset the boards. Press Ctrl+C after the Show and the final
complete ``stats`` line seen on each port is printed again as a summary.
"""

from __future__ import annotations

import argparse
import threading
import time
from dataclasses import dataclass
from datetime import datetime

import serial


@dataclass
class PortState:
    port: str
    serial_port: serial.Serial
    last_stats: str | None = None
    error: str | None = None


def _open_without_reset(port: str, baudrate: int) -> serial.Serial:
    connection = serial.Serial()
    connection.port = port
    connection.baudrate = baudrate
    connection.timeout = 0.2
    connection.write_timeout = 0.2
    connection.dtr = False
    connection.rts = False
    connection.open()
    return connection


def _timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def _reader(
    state: PortState,
    stop: threading.Event,
    print_lock: threading.Lock,
    stats_only: bool,
) -> None:
    pending = bytearray()
    try:
        while not stop.is_set():
            waiting = state.serial_port.in_waiting
            chunk = state.serial_port.read(waiting if waiting > 0 else 1)
            if not chunk:
                continue
            pending.extend(chunk)
            while b"\n" in pending:
                raw_line, _, remainder = pending.partition(b"\n")
                pending = bytearray(remainder)
                line = raw_line.rstrip(b"\r").decode("utf-8", errors="replace")
                is_stats = "stats" in line.lower()
                if is_stats:
                    state.last_stats = line
                if not stats_only or is_stats:
                    with print_lock:
                        print(f"{_timestamp()} [{state.port}] {line}", flush=True)
    except (OSError, serial.SerialException) as exc:
        state.error = str(exc)
        stop.set()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Monitor ESP32 serial output and retain each port's latest "
            "complete stats line."
        )
    )
    parser.add_argument(
        "--ports",
        nargs="+",
        default=["COM7", "COM13"],
        help="Serial ports to monitor (default: COM7 COM13).",
    )
    parser.add_argument("--baudrate", type=int, default=115200)
    parser.add_argument(
        "--duration",
        type=float,
        default=0.0,
        help="Stop automatically after this many seconds; 0 waits for Ctrl+C.",
    )
    parser.add_argument(
        "--stats-only",
        action="store_true",
        help="Hide non-stats lines while still consuming them.",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.duration < 0:
        raise SystemExit("--duration must be >= 0")
    if len(set(port.upper() for port in args.ports)) != len(args.ports):
        raise SystemExit("--ports must not contain duplicates")

    states: list[PortState] = []
    try:
        for port in args.ports:
            states.append(
                PortState(
                    port=port,
                    serial_port=_open_without_reset(port, args.baudrate),
                )
            )
    except (OSError, serial.SerialException) as exc:
        for state in states:
            state.serial_port.close()
        print(f"Failed to open serial ports: {exc}")
        return 2

    stop = threading.Event()
    print_lock = threading.Lock()
    threads = [
        threading.Thread(
            target=_reader,
            args=(state, stop, print_lock, args.stats_only),
            name=f"serial-{state.port}",
            daemon=True,
        )
        for state in states
    ]
    for thread in threads:
        thread.start()

    print(
        f"Monitoring {', '.join(args.ports)} at {args.baudrate} baud "
        "(DTR/RTS disabled). Press Ctrl+C after waiting 2 seconds past Show exit.",
        flush=True,
    )
    deadline = None if args.duration == 0 else time.monotonic() + args.duration
    try:
        while not stop.is_set() and (
            deadline is None or time.monotonic() < deadline
        ):
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        for thread in threads:
            thread.join(timeout=1.0)
        for state in states:
            state.serial_port.close()

    print("\nLatest complete stats lines:")
    exit_code = 0
    for state in states:
        if state.last_stats is None:
            print(f"[{state.port}] NO COMPLETE STATS LINE RECEIVED")
            exit_code = 1
        else:
            print(f"[{state.port}] {state.last_stats}")
        if state.error is not None:
            print(f"[{state.port}] SERIAL ERROR: {state.error}")
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
