from __future__ import annotations

import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
SUGGESTIONS_FILE = DATA_DIR / "material_suggestions.json"
TEXTBOOK_OUT = BASE_DIR / "MATH_TEXTBOOK_AI.md"
PRACTICE_OUT = BASE_DIR / "MATH_PRACTICE_SET_AI.md"


def load_suggestions() -> list[dict]:
    if not SUGGESTIONS_FILE.exists():
        return []
    try:
        return json.loads(SUGGESTIONS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def clean_text(value: str) -> str:
    return value.replace("\t", "\\t").replace("\r", "").strip()


def clean_list(items: list[str]) -> list[str]:
    return [clean_text(item) for item in items]


def choose_best_entries(items: list[dict]) -> list[dict]:
    best: dict[tuple[str, str], dict] = {}
    for item in items:
        key = (item.get("course", ""), item.get("unit", ""))
        current = best.get(key)
        if current is None:
            best[key] = item
            continue
        current_score = int(current.get("review_score", 0))
        new_score = int(item.get("review_score", 0))
        if new_score > current_score:
            best[key] = item
            continue
        if new_score == current_score and str(item.get("created_at", "")) > str(current.get("created_at", "")):
            best[key] = item
    return sorted(best.values(), key=lambda x: (x.get("course", ""), x.get("unit", "")))


def textbook_markdown(entries: list[dict]) -> str:
    lines = [
        "# 数学I・A・II・B AI教材ノート",
        "",
        "このノートは、ローカルAIシミュレーションで採用された教材候補を単元ごとにまとめたものです。",
        "人力で整えた本編とは別に、追加インプット用として使えます。",
        "",
    ]
    current_course = None
    for entry in entries:
        textbook = entry["textbook"]
        course = textbook["course"]
        if course != current_course:
            current_course = course
            lines.extend([f"## {course}", ""])
        lines.extend(
            [
                f"### {clean_text(textbook['unit'])}: {clean_text(textbook['title'])}",
                "",
                clean_text(textbook["overview"]),
                "",
                "#### 要点",
                "",
            ]
        )
        lines.extend([f"- {point}" for point in clean_list(textbook["core_points"])])
        lines.extend(["", f"#### 例題: {clean_text(textbook['example_title'])}", ""])
        lines.extend([f"{i}. {step}" for i, step in enumerate(clean_list(textbook["example_steps"]), start=1)])
        lines.extend(["", "#### よくあるミス", ""])
        lines.extend([f"- {item}" for item in clean_list(textbook["common_mistakes"])])
        lines.extend(["", "#### クイックチェック", ""])
        lines.extend([f"- {item}" for item in clean_list(textbook["quick_check"])])
        lines.extend(["", f"採用スコア: {entry.get('review_score', 0)}", ""])
    return "\n".join(lines).strip() + "\n"


def practice_markdown(entries: list[dict]) -> str:
    lines = [
        "# 数学I・A・II・B AI練習問題集",
        "",
        "この問題集は、ローカルAIシミュレーションで採用された練習問題候補を単元ごとにまとめたものです。",
        "",
    ]
    current_course = None
    for entry in entries:
        practice = entry["practice"]
        course = practice["course"]
        if course != current_course:
            current_course = course
            lines.extend([f"## {course}", ""])
        lines.extend([f"### {clean_text(practice['unit'])}: {clean_text(practice['title'])}", "", "#### 基礎", ""])
        lines.extend([f"{i}. {question}" for i, question in enumerate(clean_list(practice["basic_questions"]), start=1)])
        lines.extend(["", "#### 標準", ""])
        lines.extend([f"1. {question}" for question in clean_list(practice["standard_questions"])])
        lines.extend(["", "#### 答えとメモ", ""])
        for idx, (answer, note) in enumerate(zip(clean_list(practice["answers"]), clean_list(practice["answer_notes"])), start=1):
            lines.append(f"{idx}. {answer}")
            lines.append(f"   {note}")
        lines.extend(["", f"採用スコア: {entry.get('review_score', 0)}", ""])
    return "\n".join(lines).strip() + "\n"


def merge_material_suggestions() -> tuple[int, Path, Path]:
    entries = choose_best_entries(load_suggestions())
    TEXTBOOK_OUT.write_text(textbook_markdown(entries), encoding="utf-8")
    PRACTICE_OUT.write_text(practice_markdown(entries), encoding="utf-8")
    return len(entries), TEXTBOOK_OUT, PRACTICE_OUT


def main() -> None:
    count, textbook_path, practice_path = merge_material_suggestions()
    print(f"merged_units={count}")
    print(f"textbook={textbook_path}")
    print(f"practice={practice_path}")


if __name__ == "__main__":
    main()
