from __future__ import annotations

import argparse
import ctypes
import json
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from local_ai_materials_merge import merge_material_suggestions
from local_ai_materials_simulator import run_cycle as run_material_cycle
from local_ai_materials_simulator import stop_model as stop_material_model
from local_ai_simulator import run_cycle as run_question_cycle
from local_ai_simulator import stop_model as stop_question_model


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
STATE_FILE = DATA_DIR / "supervisor_state.json"

QUESTION_LIGHT_MODEL = "qwen3:4b"
QUESTION_HEAVY_MODEL = "qwen2-math:7b"
MATERIAL_MODEL = "qwen3:4b"


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


@dataclass
class Profile:
    name: str
    worker: str
    model: str
    idle_threshold: int
    min_free_gb: float
    timeout_seconds: int
    poll_seconds: int


DAY_QUESTION = Profile(
    name="day-question",
    worker="question",
    model=QUESTION_LIGHT_MODEL,
    idle_threshold=5,
    min_free_gb=4.8,
    timeout_seconds=700,
    poll_seconds=180,
)

DAY_MATERIAL = Profile(
    name="day-material",
    worker="material",
    model=MATERIAL_MODEL,
    idle_threshold=7,
    min_free_gb=5.2,
    timeout_seconds=800,
    poll_seconds=240,
)

NIGHT_QUESTION = Profile(
    name="night-question",
    worker="question",
    model=QUESTION_HEAVY_MODEL,
    idle_threshold=20,
    min_free_gb=6.4,
    timeout_seconds=1200,
    poll_seconds=300,
)

NIGHT_MATERIAL = Profile(
    name="night-material",
    worker="material",
    model=MATERIAL_MODEL,
    idle_threshold=15,
    min_free_gb=5.4,
    timeout_seconds=900,
    poll_seconds=300,
)


def idle_minutes() -> float:
    info = LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(info)
    ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info))
    millis = ctypes.windll.kernel32.GetTickCount() - info.dwTime
    return millis / 1000.0 / 60.0


def free_memory_gb() -> float:
    status = MEMORYSTATUSEX()
    status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
    return status.ullAvailPhys / (1024**3)


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def is_night_hour(hour: int) -> bool:
    return hour >= 23 or hour < 7


def load_state() -> dict[str, Any]:
    default_state = {
        "next_worker": "question",
        "last_profile": "",
        "last_run_at": "",
        "cycles": 0,
        "night_material_streak": 0,
        "last_decision": "",
        "last_free_gb": 0.0,
        "last_idle_minutes": 0.0,
        "last_merged_units": 0,
    }
    if not STATE_FILE.exists():
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(default_state, ensure_ascii=False, indent=2), encoding="utf-8")
        return default_state
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default_state
    return {
        "next_worker": str(state.get("next_worker", "question")),
        "last_profile": str(state.get("last_profile", "")),
        "last_run_at": str(state.get("last_run_at", "")),
        "cycles": int(state.get("cycles", 0)),
        "night_material_streak": int(state.get("night_material_streak", 0)),
        "last_decision": str(state.get("last_decision", "")),
        "last_free_gb": float(state.get("last_free_gb", 0.0)),
        "last_idle_minutes": float(state.get("last_idle_minutes", 0.0)),
        "last_merged_units": int(state.get("last_merged_units", 0)),
    }


def save_state(state: dict[str, Any]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def stop_all_models() -> None:
    for model in [QUESTION_LIGHT_MODEL, QUESTION_HEAVY_MODEL, MATERIAL_MODEL]:
        stop_question_model(model)
        stop_material_model(model)


def choose_profile(state: dict[str, Any]) -> tuple[Profile | None, str]:
    current_hour = datetime.now().hour
    idle = idle_minutes()
    free_gb = free_memory_gb()
    if free_gb < 3.5:
        stop_all_models()
        return None, f"free memory too low: {free_gb:.1f} GB"
    next_worker = state["next_worker"]
    if is_night_hour(current_hour):
        profile = NIGHT_QUESTION if next_worker == "question" else NIGHT_MATERIAL
    else:
        profile = DAY_QUESTION if next_worker == "question" else DAY_MATERIAL
    if idle < profile.idle_threshold:
        return None, f"idle {idle:.1f} min < threshold {profile.idle_threshold} min"
    if free_gb < profile.min_free_gb:
        stop_all_models()
        return None, f"free memory {free_gb:.1f} GB < needed {profile.min_free_gb:.1f} GB"
    return profile, f"profile={profile.name} idle={idle:.1f} free={free_gb:.1f} GB"


def run_profile(profile: Profile) -> None:
    if profile.worker == "question":
        run_question_cycle(
            generator_model=profile.model,
            reviewer_model=None,
            idle_threshold=0,
            sleep_seconds=0,
            timeout_seconds=profile.timeout_seconds,
            max_jobs_per_cycle=1,
            stop_models_after_job=True,
        )
        return
    run_material_cycle(
        generator_model=profile.model,
        reviewer_model=None,
        idle_threshold=0,
        sleep_seconds=0,
        timeout_seconds=profile.timeout_seconds,
        max_jobs_per_cycle=1,
        stop_models_after_job=True,
    )
    merge_material_suggestions()


def step(dry_run: bool = False) -> int:
    state = load_state()
    profile, reason = choose_profile(state)
    state["last_decision"] = reason
    state["last_free_gb"] = round(free_memory_gb(), 2)
    state["last_idle_minutes"] = round(idle_minutes(), 2)
    print(f"[{now_text()}] {reason}")
    if not profile:
        save_state(state)
        return 180
    if not dry_run:
        run_profile(profile)
        if is_night_hour(datetime.now().hour):
            if profile.worker == "question":
                state["next_worker"] = "material"
                state["night_material_streak"] = 0
            else:
                streak = int(state.get("night_material_streak", 0))
                if streak == 0:
                    state["next_worker"] = "material"
                    state["night_material_streak"] = 1
                else:
                    state["next_worker"] = "question"
                    state["night_material_streak"] = 0
        else:
            state["next_worker"] = "material" if profile.worker == "question" else "question"
            state["night_material_streak"] = 0
        state["last_profile"] = profile.name
        state["last_run_at"] = now_text()
        state["cycles"] = int(state.get("cycles", 0)) + 1
        if profile.worker == "material":
            state["last_merged_units"] = merge_material_suggestions()[0]
        save_state(state)
    return profile.poll_seconds


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--sleep-seconds", type=int, default=120, help="fallback wait between checks")
    args = parser.parse_args()

    if args.loop:
        print("supervisor loop started")
        while True:
            try:
                next_wait = step(dry_run=args.dry_run)
            except Exception as exc:
                print(f"[{now_text()}] supervisor error: {exc}")
                next_wait = args.sleep_seconds
            time.sleep(max(30, next_wait))
    else:
        step(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
