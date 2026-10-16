"""Measure process launch to the first window paint without modifying library data."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time


def child(root, output=None):
    started = time.perf_counter()
    if not getattr(sys, "frozen", False):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from PySide6.QtCore import QEvent, QObject, QTimer
    from PySide6.QtWidgets import QApplication
    from workshop.gui import WorkshopApp
    imported = time.perf_counter()
    application = QApplication([])
    application.setStyle("Fusion")
    window = WorkshopApp(root)
    built = time.perf_counter()

    def finish():
        report = {"imports_ms": round((imported-started)*1000, 1),
                          "build_ms": round((built-imported)*1000, 1),
                          "child_to_paint_ms": round((time.perf_counter()-started)*1000, 1),
                          "paint_clock": time.perf_counter()}
        if output:
            output.write_text(json.dumps(report), encoding="utf-8")
        else:
            print(json.dumps(report), flush=True)
        window.poll_timer.stop()
        window.preview_timer.stop()
        window.runner.close()
        window.runner.thread.join(3)
        window.ready_to_close = True
        window.close()
        application.quit()

    class FirstPaint(QObject):
        seen = False

        def eventFilter(self, watched, event):
            if event.type() == QEvent.Type.Paint and not self.seen:
                self.seen = True
                QTimer.singleShot(0, finish)
            return False

    observer = FirstPaint(window)
    window.installEventFilter(observer)
    window.show()
    return application.exec()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--child", action="store_true")
    parser.add_argument("--executable", type=Path)
    args = parser.parse_args()
    if args.child:
        return child(args.root.resolve())
    rows = []
    for _ in range(args.runs):
        started = time.perf_counter()
        import tempfile
        with tempfile.TemporaryDirectory(prefix="workshop-startup-") as temporary:
            report = Path(temporary) / "paint.json"
            command = ([str(args.executable.resolve()), "--startup-probe", str(args.root.resolve()), str(report)] if args.executable
                       else [sys.executable, "-B", str(Path(__file__).resolve()), "--child", "--root", str(args.root.resolve())])
            process = subprocess.Popen(command,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if args.executable:
                _, errors = process.communicate(timeout=20)
                row = json.loads(report.read_text(encoding="utf-8")) if report.exists() else None
                elapsed = round((row["paint_clock"] - started)*1000, 1) if row else 0
            else:
                line = process.stdout.readline()
                elapsed = round((time.perf_counter()-started)*1000, 1)
                _, errors = process.communicate(timeout=15)
                row = json.loads(line) if line else None
            if process.returncode or row is None:
                raise RuntimeError(errors or "No first-paint measurement returned")
        row.pop("paint_clock", None)
        row["process_to_paint_ms"] = elapsed
        rows.append(row)
    result = {"root": str(args.root.resolve()), "runs": rows,
              "median_ms": statistics.median(row["process_to_paint_ms"] for row in rows),
              "boundary": "process creation through first Qt window paint; OS desktop composition and cold boot are not measured"}
    if args.output:
        args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
