from __future__ import annotations

from dataclasses import dataclass
import psutil


@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    name: str
    exe: str

    @property
    def display(self) -> str:
        return f"{self.name}  [PID {self.pid}]"


def list_processes() -> list[ProcessInfo]:
    result: list[ProcessInfo] = []
    for proc in psutil.process_iter(["pid", "name", "exe"]):
        try:
            name = proc.info.get("name") or ""
            if not name:
                continue
            result.append(
                ProcessInfo(
                    pid=int(proc.info["pid"]),
                    name=name,
                    exe=proc.info.get("exe") or "",
                )
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    result.sort(key=lambda p: (p.name.casefold(), p.pid))
    return result


def find_matching_process(pattern: str) -> ProcessInfo | None:
    needle = pattern.strip().casefold()
    if not needle:
        return None
    for proc in list_processes():
        if needle in f"{proc.name}\n{proc.exe}".casefold():
            return proc
    return None
