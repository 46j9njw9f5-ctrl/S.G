from __future__ import annotations

import argparse
import ctypes
import json
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
JOBS_FILE = DATA_DIR / "material_jobs.json"
STATE_FILE = DATA_DIR / "material_simulation_state.json"
RESULTS_FILE = DATA_DIR / "material_suggestions.json"
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"


MATERIAL_PROMPT = """あなたは高校数学の教材編集者です。
対象:
- コース: {course}
- 単元: {unit}
- 重点: {focus}

要件:
- スマホで読みやすい短めの教科書ブロックを1つ作る
- 続けて、その単元の練習問題ブロックを1つ作る
- 数学的に正確
- 市販教材の本文を模倣しない
- 途中式や計算根拠を省略しない
- 解説は「なぜそうするか」が伝わるようにする
- JSONのみ返す

textbook は次を返す:
- course
- unit
- focus
- title
- overview (120字以内)
- core_points (3-5個)
- example_title
- example_steps (2-4個)
- common_mistakes (2-4個)
- quick_check (2-4個)
- example_steps は4-6個にする
- example_steps には実際の計算結果を含める
- overview は80字以上120字以内を目安にする

practice は次を返す:
- course
- unit
- focus
- title
- basic_questions (2個)
- standard_questions (1個)
- answers (3個)
- answer_notes (3個)
- answer_notes は各20字以上で、途中計算か判断根拠を含める
- answer と answer_notes の内容は一致させる
"""


MATERIAL_REVIEW_PROMPT = """あなたは高校数学教材の査読者です。
入力された教材ブロックについて、次を JSON で返してください。
- accepted: true/false
- score: 0-100
- reason: 短い理由

採点基準:
- 数学的正確性
- スマホでの読みやすさ
- 単元と focus への一致
- そのまま教科書や問題集に入れられる自然さ
- 途中式と計算根拠の十分さ
- answer と answer_notes の整合性
"""


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


def idle_seconds() -> float:
    info = LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(info)
    ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info))
    millis = ctypes.windll.kernel32.GetTickCount() - info.dwTime
    return millis / 1000.0


def idle_minutes() -> float:
    return idle_seconds() / 60.0


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_state() -> dict[str, Any]:
    default_state = {"next_job_index": 0, "total_cycles": 0, "last_run_at": ""}
    if not STATE_FILE.exists():
        save_json(STATE_FILE, default_state)
    state = load_json(STATE_FILE, default_state)
    if not isinstance(state, dict):
        return default_state
    return {
        "next_job_index": int(state.get("next_job_index", 0)),
        "total_cycles": int(state.get("total_cycles", 0)),
        "last_run_at": str(state.get("last_run_at", "")),
    }


def save_state(state: dict[str, Any]) -> None:
    save_json(STATE_FILE, state)


def parse_json_content(content: str) -> Any:
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if "\n" in cleaned:
            cleaned = cleaned.split("\n", 1)[1]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
    try:
        return json.loads(cleaned)
    except JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(cleaned[start : end + 1])
        raise


def ollama_chat(model: str, prompt: str, schema: dict[str, Any] | None = None, timeout_seconds: int = 900) -> Any:
    payload: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "think": False,
        "options": {
            "temperature": 0.2,
            "top_p": 0.8,
            "num_ctx": 4096,
            "num_predict": 1100,
        },
    }
    if schema:
        payload["format"] = schema
    request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        raw = json.loads(response.read().decode("utf-8"))
    return parse_json_content(raw["message"]["content"])


def stop_model(model: str) -> None:
    try:
        subprocess.run(
            ["ollama", "stop", model],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
    except Exception:
        return


def material_schema() -> dict[str, Any]:
    string_array = {"type": "array", "items": {"type": "string"}}
    return {
        "type": "object",
        "properties": {
            "textbook": {
                "type": "object",
                "properties": {
                    "course": {"type": "string"},
                    "unit": {"type": "string"},
                    "focus": {"type": "string"},
                    "title": {"type": "string"},
                    "overview": {"type": "string"},
                    "core_points": string_array,
                    "example_title": {"type": "string"},
                    "example_steps": string_array,
                    "common_mistakes": string_array,
                    "quick_check": string_array,
                },
                "required": [
                    "course",
                    "unit",
                    "focus",
                    "title",
                    "overview",
                    "core_points",
                    "example_title",
                    "example_steps",
                    "common_mistakes",
                    "quick_check",
                ],
            },
            "practice": {
                "type": "object",
                "properties": {
                    "course": {"type": "string"},
                    "unit": {"type": "string"},
                    "focus": {"type": "string"},
                    "title": {"type": "string"},
                    "basic_questions": string_array,
                    "standard_questions": string_array,
                    "answers": string_array,
                    "answer_notes": string_array,
                },
                "required": [
                    "course",
                    "unit",
                    "focus",
                    "title",
                    "basic_questions",
                    "standard_questions",
                    "answers",
                    "answer_notes",
                ],
            },
        },
        "required": ["textbook", "practice"],
    }


def review_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "accepted": {"type": "boolean"},
            "score": {"type": "integer"},
            "reason": {"type": "string"},
        },
        "required": ["accepted", "score", "reason"],
    }


def validate_material(result: dict[str, Any], job: dict[str, Any]) -> tuple[bool, str]:
    textbook = result.get("textbook", {})
    practice = result.get("practice", {})
    for block in [textbook, practice]:
        if block.get("course") != job["course"] or block.get("unit") != job["unit"]:
            return False, "course/unit mismatch"
    if len(textbook.get("core_points", [])) < 3:
        return False, "textbook core_points too short"
    if len(textbook.get("example_steps", [])) < 4:
        return False, "textbook example_steps too short"
    if len(str(textbook.get("overview", "")).strip()) < 45:
        return False, "textbook overview too short"
    if len(practice.get("basic_questions", [])) != 2:
        return False, "practice basic_questions must be 2"
    if len(practice.get("standard_questions", [])) != 1:
        return False, "practice standard_questions must be 1"
    if len(practice.get("answers", [])) != 3 or len(practice.get("answer_notes", [])) != 3:
        return False, "practice answer sizes mismatch"
    suspicious_fragments = ["誤り", "再考が必要", "ここでは誤り", "using", "contingency", "頂:"]
    serialized = json.dumps(result, ensure_ascii=False)
    if any(fragment in serialized for fragment in suspicious_fragments):
        return False, "suspicious wording found"
    short_notes = [note for note in practice.get("answer_notes", []) if len(str(note).strip()) < 20]
    if short_notes:
        return False, "answer_notes too short"
    return True, ""


def review_material(result: dict[str, Any], reviewer_model: str | None, timeout_seconds: int) -> tuple[bool, int, str]:
    if not reviewer_model:
        return False, 0, "review model required"
    prompt = MATERIAL_REVIEW_PROMPT + "\n\n" + json.dumps(result, ensure_ascii=False, indent=2)
    review = ollama_chat(reviewer_model, prompt, review_schema(), timeout_seconds=timeout_seconds)
    accepted = bool(review["accepted"]) and int(review["score"]) >= 75
    return accepted, int(review["score"]), str(review["reason"])


def load_jobs() -> list[dict[str, Any]]:
    default_jobs = [
        {"course": "数学I", "unit": "二次関数", "focus": "最大最小と定義域"},
        {"course": "数学A", "unit": "確率", "focus": "余事象と全事象"},
        {"course": "数学II", "unit": "微分法", "focus": "接線と増減"},
        {"course": "数学B", "unit": "数列", "focus": "一般項と和"},
    ]
    if not JOBS_FILE.exists():
        save_json(JOBS_FILE, default_jobs)
    return load_json(JOBS_FILE, default_jobs)


def append_result(job: dict[str, Any], result: dict[str, Any], score: int, reason: str) -> None:
    results = load_json(RESULTS_FILE, [])
    results.append(
        {
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "course": job["course"],
            "unit": job["unit"],
            "focus": job["focus"],
            "review_score": score,
            "review_reason": reason,
            "textbook": result["textbook"],
            "practice": result["practice"],
        }
    )
    save_json(RESULTS_FILE, results)


@dataclass
class RunStats:
    generated: int = 0
    accepted: int = 0
    rejected: int = 0


def process_job(job: dict[str, Any], generator_model: str, reviewer_model: str | None, timeout_seconds: int) -> RunStats:
    stats = RunStats()
    result = ollama_chat(generator_model, MATERIAL_PROMPT.format(**job), material_schema(), timeout_seconds=timeout_seconds)
    stats.generated = 1
    valid, reason = validate_material(result, job)
    if not valid:
        stats.rejected = 1
        return stats
    accepted, score, review_reason = review_material(result, reviewer_model, timeout_seconds)
    if accepted:
        append_result(job, result, score, review_reason)
        stats.accepted = 1
    else:
        stats.rejected = 1
    return stats


def run_cycle(
    generator_model: str,
    reviewer_model: str | None,
    idle_threshold: int,
    sleep_seconds: int,
    timeout_seconds: int,
    max_jobs_per_cycle: int,
    stop_models_after_job: bool,
) -> None:
    jobs = load_jobs()
    if idle_minutes() < idle_threshold:
        print(f"idle {idle_minutes():.1f} min < threshold {idle_threshold} min, skip")
        return
    if not jobs:
        print("no material jobs configured")
        return
    state = load_state()
    start_index = state["next_job_index"] % len(jobs)
    processed = 0
    for offset in range(len(jobs)):
        if processed >= max_jobs_per_cycle:
            break
        if idle_minutes() < idle_threshold:
            print("user active again, stopping cycle")
            return
        job_index = (start_index + offset) % len(jobs)
        job = jobs[job_index]
        print(f"material job: {job['course']} / {job['unit']} / {job['focus']}")
        stats = process_job(job, generator_model, reviewer_model, timeout_seconds)
        print(f"generated={stats.generated} accepted={stats.accepted} rejected={stats.rejected}")
        processed += 1
        state["next_job_index"] = (job_index + 1) % len(jobs)
        state["total_cycles"] += 1
        state["last_run_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        save_state(state)
        if stop_models_after_job:
            stop_model(generator_model)
            if reviewer_model:
                stop_model(reviewer_model)
        time.sleep(sleep_seconds)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generator-model", default="qwen3:4b")
    parser.add_argument("--reviewer-model", default="")
    parser.add_argument("--idle-threshold", type=int, default=8)
    parser.add_argument("--sleep-seconds", type=int, default=10)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--max-jobs-per-cycle", type=int, default=1)
    parser.add_argument("--keep-model-loaded", action="store_true")
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--poll-seconds", type=int, default=180)
    args = parser.parse_args()

    if args.loop:
        print("materials loop mode started")
        while True:
            try:
                run_cycle(
                    args.generator_model,
                    args.reviewer_model or None,
                    args.idle_threshold,
                    args.sleep_seconds,
                    args.timeout_seconds,
                    args.max_jobs_per_cycle,
                    not args.keep_model_loaded,
                )
            except urllib.error.URLError as exc:
                print(f"ollama unavailable: {exc}")
            except Exception as exc:
                print(f"cycle error: {exc}")
            time.sleep(args.poll_seconds)
    else:
        run_cycle(
            args.generator_model,
            args.reviewer_model or None,
            args.idle_threshold,
            args.sleep_seconds,
            args.timeout_seconds,
            args.max_jobs_per_cycle,
            not args.keep_model_loaded,
        )


if __name__ == "__main__":
    main()
