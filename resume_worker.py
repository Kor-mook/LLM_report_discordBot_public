from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO

import resume_queue
import work_events


SCRIPT_DIR = Path(__file__).resolve().parent
LOG_DIR = SCRIPT_DIR / "logs" / "resumed_tasks"


@dataclass
class ManagedProcess:
    process: subprocess.Popen[bytes]
    log_handle: BinaryIO


@dataclass
class ResumeWorker:
    processes: dict[str, ManagedProcess] = field(default_factory=dict)

    def poll(self) -> None:
        self._reap_finished()
        if not resume_queue.is_enabled():
            return

        for task in resume_queue.take_due_tasks():
            self._launch(task)

    def _launch(self, task: resume_queue.ResumeTask) -> None:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_path = LOG_DIR / f"{task.task_id}.log"
        log_handle: BinaryIO | None = None
        try:
            log_handle = log_path.open("ab")
            process = subprocess.Popen(
                task.command,
                cwd=task.cwd,
                stdin=subprocess.DEVNULL,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                env=os.environ.copy(),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, ValueError) as exc:
            if log_handle is not None:
                log_handle.close()
            resume_queue.update_task(task.task_id, status="failed", last_error=str(exc))
            work_events.append_event(
                "failed",
                provider=task.provider,
                session_id=task.session_id,
            )
            return

        self.processes[task.task_id] = ManagedProcess(process, log_handle)
        resume_queue.update_task(task.task_id, status="running")
        work_events.append_event(
            "start",
            provider=task.provider,
            session_id=task.session_id,
        )

    def _reap_finished(self) -> None:
        for task_id, managed in list(self.processes.items()):
            return_code = managed.process.poll()
            if return_code is None:
                continue

            managed.log_handle.close()

            task = resume_queue.update_task(
                task_id,
                status="completed" if return_code == 0 else "failed",
                last_error="" if return_code == 0 else f"process exited with {return_code}",
            )
            if task is not None:
                work_events.append_event(
                    "complete" if return_code == 0 else "failed",
                    provider=task.provider,
                    session_id=task.session_id,
                )
            del self.processes[task_id]
    def stop(self) -> None:
        """Stop every command started by this worker and release its log files."""
        for task_id, managed in list(self.processes.items()):
            process = managed.process
            if process.poll() is None and os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            elif process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    process.kill()
            managed.log_handle.close()
            del self.processes[task_id]
