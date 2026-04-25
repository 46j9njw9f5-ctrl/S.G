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
BANK_FILE = DATA_DIR / "question_bank.json"
JOBS_FILE = DATA_DIR / "simulation_jobs.json"
STATE_FILE = DATA_DIR / "simulation_state.json"
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"


PROMPT_TEMPLATE = """あなたは高校数学の良質な選択式問題作成者です。
対象:
- 科目: 数学
- コース: {course}
- 単元: {unit}
- 難易度: {difficulty}
- 重点技能: {skill_tag}

要件:
- スマホ向け4択問題を {batch_size} 問作る
- 数学的に正確
- 市販教材の本文を模倣しない
- 1問あたりの出力は簡潔にする
- 問題ごとに次を返す:
  - course
  - unit
  - concept
  - difficulty (配列)
  - skill_tag
  - quality_label ("high")
  - prompt
  - choices (4つ)
  - correct_index
  - answer_text
  - option_notes (各選択肢の短い説明4つ)
  - explanation {{type, overview, steps, pitfalls, rule}}
- explanation の制約:
  - overview は 80字以内
  - steps は 2-4個
  - 各 step は 60字以内
  - pitfalls は 1-3個
  - rule は 60字以内
- JSONのみ返す
"""


REVIEW_PROMPT = """あなたは高校数学の選択式問題の査読者です。
入力された問題について、次を JSON で返してください。
- accepted: true/false
- score: 0-100
- reason: 短い理由

採点基準:
- 数学的正確性
- 選択肢の自然さ
- skill_tag に沿った誤答設計
- 解説の明確さ
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
            "num_predict": 900,
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
    content = raw["message"]["content"]
    return parse_json_content(content)


def stop_model(model: str) -> None:
    try:
        subprocess.run(
            ["ollama", "stop", model],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
        return
    except Exception:
        payload = {"model": model}
        request = urllib.request.Request(
            "http://127.0.0.1:11434/api/stop",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30):
                return
        except Exception:
            return


def questions_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "course": {"type": "string"},
                        "unit": {"type": "string"},
                        "concept": {"type": "string"},
                        "difficulty": {"type": "array", "items": {"type": "string"}},
                        "skill_tag": {"type": "string"},
                        "quality_label": {"type": "string"},
                        "prompt": {"type": "string"},
                        "choices": {"type": "array", "items": {"type": "string"}, "minItems": 4, "maxItems": 4},
                        "correct_index": {"type": "integer"},
                        "answer_text": {"type": "string"},
                        "option_notes": {"type": "array", "items": {"type": "string"}, "minItems": 4, "maxItems": 4},
                        "explanation": {
                            "type": "object",
                            "properties": {
                                "type": {"type": "string"},
                                "overview": {"type": "string"},
                                "steps": {"type": "array", "items": {"type": "string"}},
                                "pitfalls": {"type": "array", "items": {"type": "string"}},
                                "rule": {"type": "string"},
                            },
                            "required": ["type", "overview", "steps", "pitfalls", "rule"],
                        },
                    },
                    "required": [
                        "course",
                        "unit",
                        "concept",
                        "difficulty",
                        "skill_tag",
                        "quality_label",
                        "prompt",
                        "choices",
                        "correct_index",
                        "answer_text",
                        "option_notes",
                        "explanation",
                    ],
                },
            }
        },
        "required": ["items"],
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


def validate_question(item: dict[str, Any], job: dict[str, Any]) -> tuple[bool, str]:
    if item.get("course") != job["course"] or item.get("unit") != job["unit"]:
        return False, "course/unit mismatch"
    choices = item.get("choices", [])
    if len(choices) != 4 or len(set(choices)) != 4:
        return False, "choices must be 4 unique entries"
    correct_index = item.get("correct_index")
    if correct_index not in [0, 1, 2, 3]:
        return False, "correct_index out of range"
    if item.get("choices", [])[correct_index] != item.get("answer_text"):
        return False, "answer_text mismatch"
    if len(item.get("option_notes", [])) != 4:
        return False, "option_notes size mismatch"
    return True, ""


def review_question(item: dict[str, Any], reviewer_model: str | None, timeout_seconds: int) -> tuple[bool, int, str]:
    if not reviewer_model:
        return True, 75, "review skipped"
    prompt = REVIEW_PROMPT + "\n\n" + json.dumps(item, ensure_ascii=False, indent=2)
    result = ollama_chat(reviewer_model, prompt, review_schema(), timeout_seconds=timeout_seconds)
    accepted = bool(result["accepted"]) and int(result["score"]) >= 75
    return accepted, int(result["score"]), str(result["reason"])


def append_bank(items: list[dict[str, Any]]) -> None:
    bank = load_json(BANK_FILE, [])
    bank.extend(items)
    save_json(BANK_FILE, bank)


def load_jobs() -> list[dict[str, Any]]:
    default_jobs = [
        {"course": "数学I", "unit": "二次関数", "difficulty": "標準", "skill_tag": "定義域見落とし", "batch_size": 1},
        {"course": "数学A", "unit": "確率", "difficulty": "標準", "skill_tag": "余事象の使い忘れ", "batch_size": 1},
        {"course": "数学B", "unit": "数列", "difficulty": "標準", "skill_tag": "和の公式ミス", "batch_size": 1},
        {"course": "数学II", "unit": "微分法", "difficulty": "標準", "skill_tag": "接線式の立て方ミス", "batch_size": 1},
    ]
    if not JOBS_FILE.exists():
        save_json(JOBS_FILE, default_jobs)
    return load_json(JOBS_FILE, default_jobs)


@dataclass
class RunStats:
    generated: int = 0
    accepted: int = 0
    rejected: int = 0


def process_job(job: dict[str, Any], generator_model: str, reviewer_model: str | None, timeout_seconds: int) -> RunStats:
    stats = RunStats()
    prompt = PROMPT_TEMPLATE.format(**job)
    result = ollama_chat(generator_model, prompt, questions_schema(), timeout_seconds=timeout_seconds)
    accepted_items: list[dict[str, Any]] = []
    for item in result.get("items", []):
        stats.generated += 1
        ok, reason = validate_question(item, job)
        if not ok:
            stats.rejected += 1
            continue
        accepted, score, review_reason = review_question(item, reviewer_model, timeout_seconds)
        item["review_score"] = score
        item["review_reason"] = review_reason
        if accepted:
            accepted_items.append(item)
            stats.accepted += 1
        else:
            stats.rejected += 1
    if accepted_items:
        append_bank(accepted_items)
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
        print("no simulation jobs configured")
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
        print(f"job start: {job['course']} / {job['unit']} / {job['skill_tag']}")
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
    parser.add_argument("--idle-threshold", type=int, default=8, help="resume only after this many idle minutes")
    parser.add_argument("--sleep-seconds", type=int, default=10, help="cooldown between jobs")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--max-jobs-per-cycle", type=int, default=1, help="how many jobs to run on one idle wake")
    parser.add_argument("--keep-model-loaded", action="store_true", help="skip stopping Ollama models after each job")
    parser.add_argument("--loop", action="store_true", help="keep polling forever")
    parser.add_argument("--poll-seconds", type=int, default=120, help="when --loop is set")
    args = parser.parse_args()

    if args.loop:
        print("loop mode started")
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
