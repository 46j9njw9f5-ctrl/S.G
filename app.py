from __future__ import annotations

import base64
import json
import random
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from fractions import Fraction
from pathlib import Path
from typing import Any

import requests
import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError


APP_TITLE = "学習改善エンジン"
DATA_DIR = Path("data")
LOGS_FILE = DATA_DIR / "logs.json"
MISTAKES_FILE = DATA_DIR / "mistakes.json"
QUESTIONS_FILE = DATA_DIR / "questions.json"

SUBJECTS = ["数学", "英語", "国語", "理科", "社会", "情報", "その他"]
ACTIVE_SUBJECTS = ["数学"]
COMING_SOON_SUBJECTS = ["英語", "国語", "理科", "社会", "情報"]
MISTAKE_CATEGORIES = ["理解不足", "計算ミス", "条件見落とし", "暗記不足", "解法ミス"]
WEAKNESS_TAGS = ["定義域見落とし", "軸ミス", "場合分け忘れ", "符号ミス", "端点比較忘れ"]
DIFFICULTIES = ["基礎", "標準", "共通テスト風"]
DIFFICULTIES_WITH_AUTO = ["自動調整", "基礎", "標準", "共通テスト風"]
DOMAIN_OPTIONS = ["定義域なし", "定義域あり", "おまかせ"]
GITHUB_API_BASE = "https://api.github.com"

REVIEW_INTERVALS_CORRECT = [1, 3, 7]
REVIEW_INTERVALS_INCORRECT = [0, 1, 3]

YOUTUBE_RECOMMENDATIONS = [
    {
        "title": "超わかる！ 2次関数の最大・最小",
        "url": "https://www.youtube.com/watch?v=QrXZgYOSZ4w",
        "focus": ["軸ミス", "定義域見落とし", "端点比較忘れ"],
        "difficulty": ["基礎", "標準"],
        "reason": "平方完成、軸、範囲の3点で整理する基本型に強いです。",
    },
    {
        "title": "超わかる！ 2次関数の最大・最小 演習",
        "url": "https://youtu.be/hjsJ12VWFDs",
        "focus": ["場合分け忘れ", "端点比較忘れ"],
        "difficulty": ["標準"],
        "reason": "解法を見たあとに、そのまま演習で確認しやすい流れです。",
    },
    {
        "title": "FocusGold予備校 共通テストに出る二次関数の最大・最小",
        "url": "https://www.youtube.com/watch?v=KzRoZJ6rXac",
        "focus": ["場合分け忘れ", "符号ミス", "端点比較忘れ"],
        "difficulty": ["共通テスト風", "標準"],
        "reason": "共通テスト風の処理順を固めたいときに相性がいいです。",
    },
    {
        "title": "二次関数の最大値と最小値の求め方（記事＋動画）",
        "url": "https://rikeinvest.com/math-1/saidai-saisho/",
        "focus": ["軸ミス", "定義域見落とし"],
        "difficulty": ["基礎"],
        "reason": "短い説明で復習したいとき向けの基礎整理です。",
    },
]


@dataclass
class QuestionBundle:
    record: dict[str, Any]


def ensure_data_files() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    for path in [LOGS_FILE, MISTAKES_FILE, QUESTIONS_FILE]:
        if not path.exists():
            path.write_text("[]", encoding="utf-8")


def to_jsonable(value: Any) -> Any:
    if isinstance(value, Fraction):
        return {"__type__": "fraction", "value": f"{value.numerator}/{value.denominator}"}
    if isinstance(value, dict):
        return {key: to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    return value


def from_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        if value.get("__type__") == "fraction":
            return Fraction(value["value"])
        return {key: from_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [from_jsonable(item) for item in value]
    return value


def now_dt() -> datetime:
    return datetime.now()


def now_iso() -> str:
    return now_dt().isoformat(timespec="seconds")


def parse_iso(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def is_due(iso_text: str | None) -> bool:
    dt = parse_iso(iso_text)
    if dt is None:
        return False
    return dt <= now_dt()


def next_review_iso(review_level: int, correct: bool) -> str:
    ladder = REVIEW_INTERVALS_CORRECT if correct else REVIEW_INTERVALS_INCORRECT
    level = max(0, min(review_level, len(ladder) - 1))
    days = ladder[level]
    when = now_dt() + timedelta(days=days)
    if not correct and days == 0:
        when = now_dt() + timedelta(minutes=15)
    return when.isoformat(timespec="seconds")


def secret(name: str, default: str = "") -> str:
    try:
        return st.secrets[name] if name in st.secrets else default
    except StreamlitSecretNotFoundError:
        return default


def github_storage_enabled() -> bool:
    return bool(secret("GITHUB_TOKEN") and secret("GITHUB_REPO"))


def github_branch() -> str:
    return secret("GITHUB_BRANCH", "main")


def github_data_path() -> str:
    return secret("GITHUB_DATA_PATH", "data").strip("/") or "data"


def github_headers() -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {secret('GITHUB_TOKEN')}",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def repo_relative_path(path: Path) -> str:
    return f"{github_data_path()}/{path.name}"


def github_fetch_file(path: Path) -> tuple[list[dict[str, Any]], str | None]:
    url = f"{GITHUB_API_BASE}/repos/{secret('GITHUB_REPO')}/contents/{repo_relative_path(path)}"
    response = requests.get(url, headers=github_headers(), params={"ref": github_branch()}, timeout=20)
    if response.status_code == 404:
        return [], None
    response.raise_for_status()
    payload = response.json()
    content = base64.b64decode(payload["content"]).decode("utf-8")
    try:
        return from_jsonable(json.loads(content)), payload["sha"]
    except json.JSONDecodeError:
        return [], payload["sha"]


def github_save_file(path: Path, data: list[dict[str, Any]]) -> None:
    _, sha = github_fetch_file(path)
    url = f"{GITHUB_API_BASE}/repos/{secret('GITHUB_REPO')}/contents/{repo_relative_path(path)}"
    body: dict[str, Any] = {
        "message": f"Update {repo_relative_path(path)} from Streamlit app",
        "content": base64.b64encode(
            json.dumps(to_jsonable(data), ensure_ascii=False, indent=2).encode("utf-8")
        ).decode("utf-8"),
        "branch": github_branch(),
    }
    if sha:
        body["sha"] = sha
    response = requests.put(url, headers=github_headers(), json=body, timeout=20)
    response.raise_for_status()


def load_json(path: Path) -> list[dict[str, Any]]:
    ensure_data_files()
    if github_storage_enabled():
        try:
            data, _ = github_fetch_file(path)
            return data
        except requests.RequestException:
            st.warning("GitHub 永続保存の読み込みに失敗したため、一時ファイルを参照します。")
    try:
        return from_jsonable(json.loads(path.read_text(encoding="utf-8")))
    except json.JSONDecodeError:
        return []


def save_json(path: Path, data: list[dict[str, Any]]) -> None:
    ensure_data_files()
    path.write_text(json.dumps(to_jsonable(data), ensure_ascii=False, indent=2), encoding="utf-8")
    if github_storage_enabled():
        try:
            github_save_file(path, data)
        except requests.RequestException:
            st.error("GitHub への永続保存に失敗しました。トークンやリポジトリ設定を確認してください。")


def append_json(path: Path, item: dict[str, Any]) -> None:
    data = load_json(path)
    data.append(item)
    save_json(path, data)


def parse_number(text: str) -> Fraction | None:
    text = (text or "").strip().replace(" ", "")
    if not text:
        return None
    try:
        return Fraction(text)
    except (ValueError, ZeroDivisionError):
        return None


def fraction_to_display(value: Fraction) -> str:
    if value.denominator == 1:
        return str(value.numerator)
    return f"{value.numerator}/{value.denominator}"


def signed_term(value: int, first: bool = False, variable: str = "") -> str:
    if value == 0:
        return ""
    sign = "-" if value < 0 else "+"
    abs_value = abs(value)
    coeff = "" if abs_value == 1 and variable else str(abs_value)
    term = f"{coeff}{variable}"
    if first:
        return term if value > 0 else f"-{term}"
    return f" {sign} {term}"


def quadratic_standard_form(a: int, b: int, c: int) -> str:
    return f"{signed_term(a, first=True, variable='x^2')}{signed_term(b, variable='x')}{signed_term(c)}"


def quadratic_vertex_form(a: int, h: int, k: int) -> str:
    if h == 0:
        inner = "x"
    elif h > 0:
        inner = f"(x - {h})"
    else:
        inner = f"(x + {abs(h)})"
    k_text = ""
    if k > 0:
        k_text = f" + {k}"
    elif k < 0:
        k_text = f" - {abs(k)}"
    a_text = "" if a == 1 else "-" if a == -1 else str(a)
    return f"{a_text}{inner}^2{k_text}"


def format_domain(left: int, right: int) -> str:
    return f"{left} <= x <= {right}"


def choose_weighted(rng: random.Random, items: list[tuple[Any, int]]) -> Any:
    values = [item[0] for item in items]
    weights = [item[1] for item in items]
    return rng.choices(values, weights=weights, k=1)[0]


def pick_profile(rng: random.Random, difficulty: str, weak_focus: str, domain_request: str) -> dict[str, Any]:
    domain_required = domain_request == "定義域あり"
    domain_free = domain_request == "定義域なし"

    if weak_focus in {"定義域見落とし", "端点比較忘れ", "場合分け忘れ"}:
        domain_required = True
    if weak_focus == "軸ミス":
        domain_request = "おまかせ"

    if domain_free:
        question_type = "no_domain_single"
    elif domain_required:
        question_type = choose_weighted(
            rng,
            [
                ("domain_inside", 1 if weak_focus not in {"端点比較忘れ"} else 0),
                ("domain_left", 3 if weak_focus in {"定義域見落とし", "端点比較忘れ"} else 2),
                ("domain_right", 3 if weak_focus in {"定義域見落とし", "端点比較忘れ"} else 2),
            ],
        )
    else:
        question_type = choose_weighted(
            rng,
            [("no_domain_single", 2), ("domain_inside", 2), ("domain_left", 1), ("domain_right", 1)],
        )

    if difficulty == "基礎":
        a = choose_weighted(rng, [(1, 2), (-1, 2), (2, 1), (-2, 1)])
        h = rng.randint(-3, 3)
        k = rng.randint(-6, 6)
    elif difficulty == "標準":
        a = choose_weighted(rng, [(1, 1), (-1, 1), (2, 2), (-2, 2), (3, 1), (-3, 1)])
        h = rng.randint(-4, 4)
        k = rng.randint(-8, 8)
    else:
        a = choose_weighted(rng, [(2, 2), (-2, 2), (3, 2), (-3, 2), (4, 1), (-4, 1)])
        h = rng.randint(-5, 5)
        k = rng.randint(-10, 10)

    if weak_focus == "符号ミス" and a > 0:
        a *= -1

    return {"question_type": question_type, "a": a, "h": h, "k": k}


def make_domain(question_type: str, h: int, difficulty: str, rng: random.Random) -> tuple[int, int] | None:
    if question_type == "no_domain_single":
        return None

    span = 3 if difficulty == "基礎" else 4 if difficulty == "標準" else 5
    if question_type == "domain_inside":
        left = h - rng.randint(1, span)
        right = h + rng.randint(1, span)
    elif question_type == "domain_left":
        right = h - rng.randint(1, 2)
        left = right - rng.randint(2, span + 1)
    else:
        left = h + rng.randint(1, 2)
        right = left + rng.randint(2, span + 1)
    if left == right:
        right += 2
    return (left, right) if left < right else (right, left)


def build_answer(a: int, h: int, k: int, domain: tuple[int, int] | None) -> dict[str, Any]:
    if domain is None:
        extremum_type = "最小値" if a > 0 else "最大値"
        return {
            "mode": "single",
            "extremum_type": extremum_type,
            "value": Fraction(k),
            "x": Fraction(h),
            "axis": Fraction(h),
            "opens": "上に開く" if a > 0 else "下に開く",
        }

    left, right = domain
    left_y = Fraction(a * (left - h) ** 2 + k)
    right_y = Fraction(a * (right - h) ** 2 + k)
    vertex_y = Fraction(k)
    axis_inside = left <= h <= right
    candidates = [
        {"x": Fraction(left), "value": left_y, "label": "左端"},
        {"x": Fraction(right), "value": right_y, "label": "右端"},
    ]
    if axis_inside:
        candidates.append({"x": Fraction(h), "value": vertex_y, "label": "軸"})

    max_item = max(candidates, key=lambda item: item["value"])
    min_item = min(candidates, key=lambda item: item["value"])
    return {
        "mode": "domain_both",
        "max_value": max_item["value"],
        "max_x": max_item["x"],
        "min_value": min_item["value"],
        "min_x": min_item["x"],
        "axis": Fraction(h),
        "axis_inside": axis_inside,
        "opens": "上に開く" if a > 0 else "下に開く",
        "left_endpoint": Fraction(left),
        "right_endpoint": Fraction(right),
    }


def detect_primary_weakness(question: dict[str, Any]) -> str:
    if question["answer"]["mode"] == "single":
        if question["a"] < 0:
            return "符号ミス"
        return "軸ミス"
    if not question["answer"]["axis_inside"]:
        return "端点比較忘れ"
    if abs(question["a"]) >= 3:
        return "符号ミス"
    return "定義域見落とし"


def build_explanation_sections(question: dict[str, Any]) -> dict[str, Any]:
    answer = question["answer"]
    base_rule = "二次関数は『軸を見て、範囲を見て、頂点と端点のどこを比べるかを決める』の順で考える。"
    if answer["mode"] == "single":
        return {
            "problem_type": f"定義域なしの二次関数の {answer['extremum_type']} 問題。",
            "overview": [
                f"{question['function_style']} から軸 x = {fraction_to_display(answer['axis'])} をつかむ。",
                f"{answer['opens']}ので、頂点がそのまま {answer['extremum_type']} になる。",
            ],
            "steps": [
                f"軸は x = {fraction_to_display(answer['axis'])}。",
                f"{answer['opens']}かを確認する。",
                f"頂点の y 座標 {fraction_to_display(answer['value'])} を読む。",
                f"答えは {answer['extremum_type']} {fraction_to_display(answer['value'])}、そのとき x = {fraction_to_display(answer['x'])}。",
            ],
            "judgement": [
                "定義域がないので端点比較は不要。",
                "上に開くなら最小、下に開くなら最大を最初に決める。",
            ],
            "common_mistakes": [
                "軸の符号を逆に読む。",
                "最大値と最小値を取り違える。",
            ],
            "generalization": base_rule,
            "checklist": [
                "軸を書いたか",
                "上に開くか下に開くか確認したか",
                "求めるのが最大か最小か一致しているか",
            ],
        }

    axis_phrase = "範囲内" if answer["axis_inside"] else "範囲外"
    near_phrase = "小さく" if question["a"] > 0 else "大きく"
    return {
        "problem_type": "定義域つきの二次関数の最大値・最小値問題。",
        "overview": [
            f"軸 x = {fraction_to_display(answer['axis'])} が定義域の {axis_phrase} かを判定する。",
            "比べるべき点を先に決めてから y 値比較に進む。",
        ],
        "steps": [
            f"定義域は {format_domain(int(answer['left_endpoint']), int(answer['right_endpoint']))}。",
            f"軸は x = {fraction_to_display(answer['axis'])}。範囲の中か外かを判定する。",
            f"{answer['opens']}ので、軸に近い点ほど {near_phrase} なりやすい。",
            "頂点を使うか端点比較だけで済むかをここで決める。",
            f"最大値は {fraction_to_display(answer['max_value'])}（x = {fraction_to_display(answer['max_x'])}）、最小値は {fraction_to_display(answer['min_value'])}（x = {fraction_to_display(answer['min_x'])}）。",
        ],
        "judgement": [
            "定義域つきでは頂点だけ見て終わらない。",
            "軸が範囲外なら端点比較が主役になる。",
            "軸が範囲内なら頂点と端点の役割を分ける。",
        ],
        "common_mistakes": [
            "定義域を見ずに頂点の値をそのまま答える。",
            "軸が範囲外なのに場合分けをしない。",
            "端点を片方しか計算しない。",
        ],
        "generalization": base_rule,
        "checklist": [
            "定義域を書いたか",
            "軸が範囲内か外か判定したか",
            "比べる候補を先に決めたか",
            "頂点と端点を混同していないか",
        ],
    }


def render_explanation_sections(sections: dict[str, Any], mode: str) -> None:
    if mode == "方針だけ":
        st.write("① 問題の型")
        st.write(sections["problem_type"])
        st.write("② 解法の全体像")
        for item in sections["overview"]:
            st.write(f"- {item}")
        return

    if mode == "途中式つき":
        st.write("① 問題の型")
        st.write(sections["problem_type"])
        st.write("② 解法の全体像")
        for item in sections["overview"]:
            st.write(f"- {item}")
        st.write("③ 手順")
        for item in sections["steps"]:
            st.write(f"- {item}")
        return

    st.write("① 問題の型")
    st.write(sections["problem_type"])
    st.write("② 解法の全体像")
    for item in sections["overview"]:
        st.write(f"- {item}")
    st.write("③ 手順（詳細）")
    for item in sections["steps"]:
        st.write(f"- {item}")
    st.write("④ 判断ポイント")
    for item in sections["judgement"]:
        st.write(f"- {item}")
    st.write("⑤ よくあるミス")
    for item in sections["common_mistakes"]:
        st.write(f"- {item}")
    st.write("⑥ 一般化（ルール）")
    st.write(f"- {sections['generalization']}")
    st.write("- チェックリスト")
    for item in sections["checklist"]:
        st.write(f"- {item}")


def make_prompt(a: int, h: int, k: int, domain: tuple[int, int] | None, difficulty: str) -> tuple[str, str]:
    b = -2 * a * h
    c = a * h * h + k
    if difficulty == "基礎":
        style = quadratic_vertex_form(a, h, k)
        expression = f"f(x) = {style}"
    else:
        style = quadratic_standard_form(a, b, c)
        expression = f"f(x) = {style}"

    if domain is None:
        if a > 0:
            prompt = f"次の二次関数の最小値と、そのときの x の値を求めよ。 {expression}"
        else:
            prompt = f"次の二次関数の最大値と、そのときの x の値を求めよ。 {expression}"
    else:
        left, right = domain
        if difficulty == "共通テスト風":
            prompt = (
                "次の関数について、定義域内での最大値と最小値を求めよ。"
                f" 必要なら軸の位置と端点を比較して判断すること。 {expression}, {format_domain(left, right)}"
            )
        else:
            prompt = f"次の二次関数について、{format_domain(left, right)} の範囲での最大値と最小値を求めよ。 {expression}"
    return prompt, expression


def generate_quadratic_question(difficulty: str, domain_request: str, weak_focus: str | None = None) -> QuestionBundle:
    rng = random.Random()
    profile = pick_profile(rng, difficulty, weak_focus or "", domain_request)
    a, h, k = profile["a"], profile["h"], profile["k"]
    domain = make_domain(profile["question_type"], h, difficulty, rng)
    answer = build_answer(a, h, k, domain)
    prompt, function_style = make_prompt(a, h, k, domain, difficulty)
    sections = build_explanation_sections({"answer": answer, "a": a, "function_style": function_style})

    record = {
        "id": str(uuid.uuid4()),
        "created_at": now_iso(),
        "subject": "数学",
        "topic": "二次関数",
        "unit": "最大最小",
        "difficulty": difficulty,
        "domain_mode": "定義域なし" if domain is None else "定義域あり",
        "question_type": profile["question_type"],
        "weak_focus": weak_focus or "",
        "recommended_weakness": detect_primary_weakness({"a": a, "answer": answer}),
        "a": a,
        "h": h,
        "k": k,
        "domain": list(domain) if domain else None,
        "prompt": prompt,
        "function_style": function_style,
        "answer": answer,
        "explanation_sections": sections,
        "answered": False,
        "last_result": None,
        "last_answer": {},
        "favorite": False,
        "hold": False,
        "review_level": 0,
        "next_review_at": None,
        "review_count": 0,
        "source": "generator",
    }
    return QuestionBundle(record=record)


def recommend_difficulty(questions: list[dict[str, Any]]) -> str:
    recent = [item for item in sorted(questions, key=lambda x: x["created_at"], reverse=True) if item.get("answered")][:6]
    if not recent:
        return "基礎"
    correct = sum(1 for item in recent if item.get("last_result") == "correct")
    ratio = correct / len(recent)
    if ratio >= 0.8 and len(recent) >= 4:
        if any(item["difficulty"] == "標準" for item in recent):
            return "共通テスト風"
        return "標準"
    if ratio <= 0.45:
        return "基礎"
    return "標準"


def generate_question_batch(
    count: int,
    difficulty: str,
    domain_request: str,
    weak_focus: str | None,
    existing_questions: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    selected_difficulty = difficulty
    if difficulty == "自動調整":
        selected_difficulty = recommend_difficulty(existing_questions or [])
    return [generate_quadratic_question(selected_difficulty, domain_request, weak_focus).record for _ in range(count)]


def update_question(updated: dict[str, Any]) -> None:
    questions = load_json(QUESTIONS_FILE)
    new_questions = [updated if item["id"] == updated["id"] else item for item in questions]
    save_json(QUESTIONS_FILE, new_questions)


def toggle_question_flag(question_id: str, field: str) -> None:
    questions = load_json(QUESTIONS_FILE)
    for item in questions:
        if item["id"] == question_id:
            item[field] = not item.get(field, False)
            break
    save_json(QUESTIONS_FILE, questions)


def classify_mistake(question: dict[str, Any], user_input: dict[str, str]) -> tuple[str, str, str]:
    answer = question["answer"]
    broad = "解法ミス"
    weakness = question.get("recommended_weakness") or "軸ミス"
    note = "比較の手順を整理し直すと安定します。"

    if answer["mode"] == "single":
        user_x = parse_number(user_input.get("x", ""))
        if user_x is not None and user_x == -answer["axis"]:
            broad = "計算ミス"
            weakness = "軸ミス"
            note = "軸の符号を逆に読んだ可能性があります。"
        elif question["a"] < 0:
            broad = "条件見落とし"
            weakness = "符号ミス"
            note = "下に開く放物線なので最大値を考える必要があります。"
        return broad, weakness, note

    if not answer["axis_inside"]:
        broad = "条件見落とし"
        weakness = "定義域見落とし"
        note = "軸が範囲外なので、頂点ではなく端点比較が必要です。"
    else:
        broad = "解法ミス"
        weakness = "場合分け忘れ"
        note = "軸が範囲内なので、頂点と端点の役割を分けて考えると整理できます。"
    return broad, weakness, note


def evaluate_answer(question: dict[str, Any], user_input: dict[str, str]) -> tuple[bool, str, dict[str, Any] | None]:
    answer = question["answer"]
    if answer["mode"] == "single":
        value = parse_number(user_input.get("value", ""))
        x_value = parse_number(user_input.get("x", ""))
        correct = value == answer["value"] and x_value == answer["x"]
        feedback = (
            f"正解です。{answer['extremum_type']}は {fraction_to_display(answer['value'])}、そのとき x = {fraction_to_display(answer['x'])}。"
            if correct
            else f"今回は不正解です。{answer['extremum_type']}は {fraction_to_display(answer['value'])}、そのとき x = {fraction_to_display(answer['x'])}。"
        )
    else:
        max_value = parse_number(user_input.get("max_value", ""))
        max_x = parse_number(user_input.get("max_x", ""))
        min_value = parse_number(user_input.get("min_value", ""))
        min_x = parse_number(user_input.get("min_x", ""))
        correct = (
            max_value == answer["max_value"]
            and max_x == answer["max_x"]
            and min_value == answer["min_value"]
            and min_x == answer["min_x"]
        )
        feedback = (
            "正解です。"
            f" 最大値は {fraction_to_display(answer['max_value'])}（x = {fraction_to_display(answer['max_x'])}）、"
            f"最小値は {fraction_to_display(answer['min_value'])}（x = {fraction_to_display(answer['min_x'])}）。"
            if correct
            else "今回は不正解です。"
            f" 最大値は {fraction_to_display(answer['max_value'])}（x = {fraction_to_display(answer['max_x'])}）、"
            f"最小値は {fraction_to_display(answer['min_value'])}（x = {fraction_to_display(answer['min_x'])}）。"
        )

    if correct:
        return True, feedback, None

    broad, weakness, note = classify_mistake(question, user_input)
    mistake = {
        "id": str(uuid.uuid4()),
        "created_at": now_iso(),
        "question_id": question["id"],
        "topic": question["topic"],
        "unit": question["unit"],
        "difficulty": question["difficulty"],
        "problem": question["prompt"],
        "my_answer": user_input,
        "correct_answer": answer,
        "mistake_content": note,
        "mistake_category": broad,
        "weakness_tag": weakness,
    }
    return False, feedback, mistake


def apply_answer_result(question: dict[str, Any], correct: bool, user_input: dict[str, str]) -> dict[str, Any]:
    current_level = int(question.get("review_level", 0))
    new_level = min(current_level + 1, len(REVIEW_INTERVALS_CORRECT) - 1) if correct else 0
    question["answered"] = True
    question["last_result"] = "correct" if correct else "incorrect"
    question["last_answer"] = user_input
    question["answered_at"] = now_iso()
    question["review_level"] = new_level
    question["review_count"] = int(question.get("review_count", 0)) + 1
    question["next_review_at"] = next_review_iso(new_level, correct)
    if correct:
        question["hold"] = False
    return question


def compute_accuracy(questions: list[dict[str, Any]]) -> float:
    answered = [item for item in questions if item.get("answered")]
    if not answered:
        return 0.0
    correct = sum(1 for item in answered if item.get("last_result") == "correct")
    return correct / len(answered)


def count_by_key(items: list[dict[str, Any]], key: str, allowed: list[str] | None = None) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = item.get(key)
        if not value:
            continue
        counts[value] = counts.get(value, 0) + 1
    if allowed:
        for value in allowed:
            counts.setdefault(value, 0)
    return dict(sorted(counts.items(), key=lambda kv: kv[1], reverse=True))


def today_minutes(logs: list[dict[str, Any]]) -> int:
    today_text = str(date.today())
    return sum(int(item.get("study_minutes", 0)) for item in logs if item.get("date") == today_text)


def compute_focus_correlation(logs: list[dict[str, Any]]) -> str:
    if not logs:
        return "まだ学習ログが少ないので、集中度と学習時間の相性はこれから見えてきます。"

    best_focus = max(logs, key=lambda item: (int(item.get("focus", 0)), int(item.get("study_minutes", 0))))
    buckets = {"短時間": [], "中時間": [], "長時間": []}
    for item in logs:
        minutes = int(item.get("study_minutes", 0))
        if minutes <= 25:
            buckets["短時間"].append(int(item.get("focus", 0)))
        elif minutes <= 50:
            buckets["中時間"].append(int(item.get("focus", 0)))
        else:
            buckets["長時間"].append(int(item.get("focus", 0)))

    def average(values: list[int]) -> float:
        return sum(values) / len(values) if values else 0.0

    best_bucket = max(buckets.items(), key=lambda kv: average(kv[1]))[0]
    return (
        f"集中度が高かった記録では {best_focus.get('unit') or best_focus.get('subject')} を {best_focus.get('study_minutes', 0)} 分行っています。"
        f" ざっくり見ると {best_bucket} の学習が安定しやすい傾向です。"
    )


def weak_point_rates(mistakes: list[dict[str, Any]], questions: list[dict[str, Any]]) -> dict[str, int]:
    answered = max(1, sum(1 for item in questions if item.get("answered")))
    counts = count_by_key(mistakes, "weakness_tag", WEAKNESS_TAGS)
    return {key: int(counts.get(key, 0) * 100 / answered) for key in WEAKNESS_TAGS}


def select_video_recommendations(top_weakness: str | None, difficulty: str) -> list[dict[str, str]]:
    matches = []
    for item in YOUTUBE_RECOMMENDATIONS:
        weakness_hit = top_weakness is None or top_weakness in item["focus"]
        difficulty_hit = difficulty in item["difficulty"] or not difficulty
        if weakness_hit and difficulty_hit:
            matches.append(item)
    return matches or YOUTUBE_RECOMMENDATIONS[:3]


def build_analysis(logs: list[dict[str, Any]], mistakes: list[dict[str, Any]], questions: list[dict[str, Any]]) -> dict[str, Any]:
    accuracy = compute_accuracy(questions)
    mistake_ranking = count_by_key(mistakes, "mistake_category", MISTAKE_CATEGORIES)
    weakness_ranking = count_by_key(mistakes, "weakness_tag", WEAKNESS_TAGS)
    top_weakness = next((key for key, value in weakness_ranking.items() if value > 0), None)
    recent = sorted(questions, key=lambda item: item["created_at"], reverse=True)[:5]
    due_reviews = [item for item in questions if is_due(item.get("next_review_at"))]
    favorite_questions = [item for item in questions if item.get("favorite")]
    hold_questions = [item for item in questions if item.get("hold")]
    recommended_difficulty = recommend_difficulty(questions)

    if top_weakness == "定義域見落とし":
        next_action = "定義域つきで、軸が範囲外になる問題を 10 問解く。"
    elif top_weakness == "軸ミス":
        next_action = "軸を先に書き出す練習を入れたうえで、標準形から頂点を取る問題を 8 問解く。"
    elif top_weakness == "場合分け忘れ":
        next_action = "軸が範囲内か外かを毎回判定するチェックを入れて、定義域ありの問題を 8 問解く。"
    elif top_weakness == "符号ミス":
        next_action = "上に開くか下に開くかを先に言語化しながら、符号が混ざる問題を 8 問解く。"
    elif top_weakness == "端点比較忘れ":
        next_action = "端点比較を必ず式で残しながら、軸が範囲外の問題を 10 問解く。"
    else:
        next_action = "基礎と標準を交互に解いて、解法の型を安定させる。"

    summary = "学習データがまだ少ないため、まず 5 問ほど解いて傾向を固める。"
    if top_weakness:
        summary = f"{top_weakness} が最も多いです。次はそのパターンに絞って演習すると改善効率が高いです。"

    return {
        "today_minutes": today_minutes(logs),
        "accuracy": accuracy,
        "mistake_ranking": mistake_ranking,
        "weakness_ranking": weakness_ranking,
        "weak_rates": weak_point_rates(mistakes, questions),
        "top_weakness": top_weakness,
        "next_action": next_action,
        "summary": summary,
        "recent_questions": recent,
        "due_reviews": due_reviews,
        "favorite_questions": favorite_questions,
        "hold_questions": hold_questions,
        "recommended_difficulty": recommended_difficulty,
        "focus_correlation": compute_focus_correlation(logs),
        "videos": select_video_recommendations(top_weakness, recommended_difficulty),
    }


def render_metric_card(label: str, value: str, help_text: str = "") -> None:
    with st.container(border=True):
        st.caption(label)
        st.subheader(value)
        if help_text:
            st.write(help_text)


def app_css() -> None:
    st.markdown(
        """
        <style>
        .stApp {
            background:
                radial-gradient(circle at top right, rgba(15,118,110,0.12), transparent 28%),
                linear-gradient(180deg, #f7f4ea 0%, #eef6ff 100%);
        }
        .block-container {
            max-width: 760px;
            padding-top: 1rem;
            padding-bottom: 4rem;
        }
        @media (max-width: 640px) {
            .block-container {
                padding-left: 0.8rem;
                padding-right: 0.8rem;
                padding-top: 0.6rem;
            }
            .stTabs [data-baseweb="tab-list"] {
                gap: 0.25rem;
                overflow-x: auto;
            }
            .stTabs [data-baseweb="tab"] {
                height: 3rem;
                white-space: nowrap;
                padding-left: 0.8rem;
                padding-right: 0.8rem;
            }
        }
        h1, h2, h3 {
            letter-spacing: -0.02em;
        }
        .stButton > button, div[data-baseweb="button"] > button {
            width: 100%;
            min-height: 3rem;
            border-radius: 16px;
            font-weight: 700;
            border: none;
            background: #0f766e;
            color: white;
        }
        .stTextInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"] {
            border-radius: 14px;
        }
        div[data-testid="stMetricValue"] {
            font-size: 1.4rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def init_page() -> None:
    st.set_page_config(page_title=APP_TITLE, page_icon="📘", layout="centered")
    app_css()
    ensure_data_files()


def render_storage_status() -> None:
    if github_storage_enabled():
        st.success(f"保存モード: GitHub 永続保存 ({secret('GITHUB_REPO')} / {github_branch()})")
    else:
        st.warning("保存モード: 一時ファイル。永続化するには Streamlit secrets に GitHub 設定を追加してください。")


def render_quick_actions(analysis: dict[str, Any], questions: list[dict[str, Any]]) -> None:
    with st.container(border=True):
        st.write("今すぐやること")
        st.write(f"- 推奨難易度: {analysis['recommended_difficulty']}")
        st.write(f"- 復習キュー: {len(analysis['due_reviews'])} 問")
        st.write(f"- お気に入り: {len(analysis['favorite_questions'])} 問")
        st.write(f"- 保留: {len(analysis['hold_questions'])} 問")
        if st.button("復習キューを 3 問追加する"):
            due = analysis["due_reviews"][:3]
            if due:
                cloned = []
                for item in due:
                    new_item = dict(item)
                    new_item["id"] = str(uuid.uuid4())
                    new_item["created_at"] = now_iso()
                    new_item["source"] = "review_queue"
                    new_item["answered"] = False
                    new_item["last_result"] = None
                    new_item["last_answer"] = {}
                    new_item["hold"] = False
                    cloned.append(new_item)
                questions.extend(cloned)
                save_json(QUESTIONS_FILE, questions)
                st.success("復習用に 3 問追加しました。")
                st.rerun()
            st.info("今は復習期限が来ている問題がありません。")


def render_home(logs: list[dict[str, Any]], mistakes: list[dict[str, Any]], questions: list[dict[str, Any]], analysis: dict[str, Any]) -> None:
    st.subheader("今日の状況")
    col1, col2 = st.columns(2)
    with col1:
        render_metric_card("学習時間", f"{analysis['today_minutes']} 分")
    with col2:
        render_metric_card("正答率", f"{int(analysis['accuracy'] * 100)}%")

    col3, col4 = st.columns(2)
    with col3:
        render_metric_card("復習キュー", f"{len(analysis['due_reviews'])} 問")
    with col4:
        render_metric_card("次の難易度", analysis["recommended_difficulty"])

    render_metric_card("弱点", analysis["top_weakness"] or "まだ分析中", analysis["summary"])
    render_metric_card("次にやること", analysis["next_action"])
    render_quick_actions(analysis, questions)

    with st.expander("学習ログを追加", expanded=False):
        with st.form("study_log_form", clear_on_submit=True):
            log_date = st.date_input("日付", value=date.today())
            subject = st.selectbox("科目", SUBJECTS)
            unit = st.text_input("単元", placeholder="二次関数 / 英文法 など")
            study_minutes = st.number_input("学習時間（分）", min_value=0, max_value=600, value=30, step=10)
            focus = st.slider("集中度", 1, 5, 3)
            content = st.text_area("内容", placeholder="短く話すように入れてOK。スマホの音声キーボードとも相性が良いです。")
            submitted = st.form_submit_button("学習ログを保存")
            if submitted:
                append_json(
                    LOGS_FILE,
                    {
                        "id": str(uuid.uuid4()),
                        "created_at": now_iso(),
                        "date": str(log_date),
                        "subject": subject,
                        "unit": unit,
                        "study_minutes": int(study_minutes),
                        "focus": focus,
                        "content": content,
                    },
                )
                st.success("学習ログを保存しました。")
                st.rerun()

    with st.expander("ミスを手動で記録", expanded=False):
        with st.form("manual_mistake_form", clear_on_submit=True):
            problem = st.text_area("問題")
            my_answer = st.text_area("自分の解答")
            correct_answer = st.text_area("正答")
            mistake_content = st.text_area("ミス内容", placeholder="何をどう間違えたか")
            category = st.selectbox("ミス分類", MISTAKE_CATEGORIES)
            weakness = st.selectbox("苦手パターン", WEAKNESS_TAGS)
            submitted = st.form_submit_button("ミスを保存")
            if submitted:
                append_json(
                    MISTAKES_FILE,
                    {
                        "id": str(uuid.uuid4()),
                        "created_at": now_iso(),
                        "question_id": "",
                        "topic": "二次関数",
                        "unit": "最大最小",
                        "difficulty": "",
                        "problem": problem,
                        "my_answer": my_answer,
                        "correct_answer": correct_answer,
                        "mistake_content": mistake_content,
                        "mistake_category": category,
                        "weakness_tag": weakness,
                    },
                )
                st.success("ミス記録を保存しました。")
                st.rerun()

    with st.container(border=True):
        st.write("学習時間との相性")
        st.write(analysis["focus_correlation"])

    st.subheader("最近の問題")
    recent = sorted(questions, key=lambda item: item["created_at"], reverse=True)[:4]
    if not recent:
        st.info("まだ問題がありません。『問題生成』タブから作成してください。")
    for item in recent:
        with st.container(border=True):
            badge = []
            if item.get("favorite"):
                badge.append("お気に入り")
            if item.get("hold"):
                badge.append("保留")
            if is_due(item.get("next_review_at")):
                badge.append("復習期限")
            st.write(item["prompt"])
            st.caption(f"{item['difficulty']} / {item['domain_mode']} / 推奨補強: {item['recommended_weakness']} {' / '.join(badge)}")
            if item.get("last_result"):
                st.write(f"直近結果: {'正解' if item['last_result'] == 'correct' else '不正解'}")


def render_video_recommendations(analysis: dict[str, Any]) -> None:
    st.subheader("おすすめ解説")
    videos = analysis["videos"]
    featured = videos[0]
    st.video(featured["url"])
    st.caption(f"{featured['title']} - {featured['reason']}")
    for item in videos:
        st.write(f"- [{item['title']}]({item['url']})")
        st.caption(item["reason"])


def render_problem_tab(logs: list[dict[str, Any]], mistakes: list[dict[str, Any]], questions: list[dict[str, Any]], analysis: dict[str, Any]) -> None:
    st.subheader("問題生成")
    with st.container(border=True):
        st.write("学習モード")
        st.write("- 利用可能: 数学（二次関数の最大最小）")
        st.write(f"- 追加予定: {', '.join(COMING_SOON_SUBJECTS)}")
        st.write("- 将来拡張しやすいように、科目ごとの保存構造は先に入れています。")

    with st.form("generate_questions_form"):
        difficulty = st.selectbox("難易度", DIFFICULTIES_WITH_AUTO, index=0)
        domain_request = st.selectbox("定義域", DOMAIN_OPTIONS)
        weak_focus = st.selectbox("苦手対応", ["おまかせ"] + WEAKNESS_TAGS)
        count = st.slider("問題数", 1, 10, 3)
        submitted = st.form_submit_button("問題を生成する")
        if submitted:
            generated = generate_question_batch(
                count=count,
                difficulty=difficulty,
                domain_request=domain_request,
                weak_focus=None if weak_focus == "おまかせ" else weak_focus,
                existing_questions=questions,
            )
            questions.extend(generated)
            save_json(QUESTIONS_FILE, questions)
            picked_difficulty = generated[0]["difficulty"] if generated else difficulty
            st.success(f"{count} 問生成しました。今回の難易度は {picked_difficulty} です。")
            st.rerun()

    quick_col1, quick_col2 = st.columns(2)
    with quick_col1:
        if st.button("弱点に合わせて 5 問作る"):
            focus = analysis["top_weakness"] or "定義域見落とし"
            generated = generate_question_batch(5, "自動調整", "定義域あり", focus, questions)
            questions.extend(generated)
            save_json(QUESTIONS_FILE, questions)
            st.success("弱点向けに 5 問追加しました。")
            st.rerun()
    with quick_col2:
        if st.button("共通テスト風を 3 問作る"):
            generated = generate_question_batch(3, "共通テスト風", "定義域あり", analysis["top_weakness"], questions)
            questions.extend(generated)
            save_json(QUESTIONS_FILE, questions)
            st.success("共通テスト風の問題を追加しました。")
            st.rerun()

    st.subheader("生成済み問題")
    latest = sorted(load_json(QUESTIONS_FILE), key=lambda item: item["created_at"], reverse=True)[:6]
    if not latest:
        st.info("まだ問題はありません。")
    for item in latest:
        with st.container(border=True):
            st.write(item["prompt"])
            review_text = "復習キューなし"
            if item.get("next_review_at"):
                review_text = f"次回復習: {item['next_review_at'].replace('T', ' ')}"
            st.caption(
                f"{item['difficulty']} / {item['domain_mode']} / 苦手対応: {item.get('weak_focus') or 'おまかせ'} / {review_text}"
            )
            explanation_mode = st.radio(
                "解説表示",
                ["方針だけ", "途中式つき", "完全版"],
                horizontal=True,
                key=f"explain_mode_{item['id']}",
            )
            with st.expander("解説を見る"):
                render_explanation_sections(item["explanation_sections"], explanation_mode)

    render_video_recommendations(analysis)


def filter_question_pool(questions: list[dict[str, Any]], mode: str) -> list[dict[str, Any]]:
    ordered = sorted(questions, key=lambda item: item["created_at"], reverse=True)
    if mode == "復習期限だけ":
        return [item for item in ordered if is_due(item.get("next_review_at"))]
    if mode == "お気に入り":
        return [item for item in ordered if item.get("favorite")]
    if mode == "保留":
        return [item for item in ordered if item.get("hold")]
    return ordered


def render_question_actions(question: dict[str, Any]) -> None:
    col1, col2 = st.columns(2)
    with col1:
        label = "お気に入り解除" if question.get("favorite") else "お気に入り登録"
        if st.button(label, key=f"fav_{question['id']}"):
            toggle_question_flag(question["id"], "favorite")
            st.rerun()
    with col2:
        label = "保留解除" if question.get("hold") else "あとで解く"
        if st.button(label, key=f"hold_{question['id']}"):
            toggle_question_flag(question["id"], "hold")
            st.rerun()


def render_answer_tab() -> None:
    st.subheader("解答")
    questions = load_json(QUESTIONS_FILE)
    if not questions:
        st.info("先に問題を生成してください。")
        return

    mode = st.segmented_control("表示", ["すべて", "復習期限だけ", "お気に入り", "保留"], default="すべて")
    pool = filter_question_pool(questions, mode or "すべて")
    if not pool:
        st.info("この条件に合う問題はまだありません。")
        return

    labels = [f"{item['created_at']} | {item['difficulty']} | {item['prompt'][:24]}..." for item in pool]
    selected_label = st.selectbox("問題を選ぶ", labels)
    question = pool[labels.index(selected_label)]

    with st.container(border=True):
        st.write(question["prompt"])
        st.caption(
            f"推奨補強: {question['recommended_weakness']} / 次回復習: {question.get('next_review_at') or '未設定'}"
        )
    render_question_actions(question)

    explanation_mode = st.radio("解説の出し方", ["方針だけ", "途中式つき", "完全版"], horizontal=True)
    answer = question["answer"]
    form_key = f"answer_form_{question['id']}"
    with st.form(form_key):
        if answer["mode"] == "single":
            value = st.text_input("値", placeholder="例: -3 または 5/2")
            x_value = st.text_input("そのときの x", placeholder="例: 2")
            submitted = st.form_submit_button("判定する")
            if submitted:
                correct, feedback, mistake = evaluate_answer(question, {"value": value, "x": x_value})
                updated = apply_answer_result(question, correct, {"value": value, "x": x_value})
                update_question(updated)
                if mistake:
                    append_json(MISTAKES_FILE, mistake)
                if correct:
                    st.success(feedback)
                else:
                    st.error(feedback)
                with st.expander("解説", expanded=True):
                    render_explanation_sections(question["explanation_sections"], explanation_mode)
        else:
            max_value = st.text_input("最大値", placeholder="例: 8")
            max_x = st.text_input("最大になる x", placeholder="例: -1")
            min_value = st.text_input("最小値", placeholder="例: -4")
            min_x = st.text_input("最小になる x", placeholder="例: 2")
            submitted = st.form_submit_button("判定する")
            if submitted:
                user_input = {
                    "max_value": max_value,
                    "max_x": max_x,
                    "min_value": min_value,
                    "min_x": min_x,
                }
                correct, feedback, mistake = evaluate_answer(question, user_input)
                updated = apply_answer_result(question, correct, user_input)
                update_question(updated)
                if mistake:
                    append_json(MISTAKES_FILE, mistake)
                if correct:
                    st.success(feedback)
                else:
                    st.error(feedback)
                with st.expander("解説", expanded=True):
                    render_explanation_sections(question["explanation_sections"], explanation_mode)


def render_analysis_tab(logs: list[dict[str, Any]], mistakes: list[dict[str, Any]], questions: list[dict[str, Any]]) -> None:
    st.subheader("分析")
    analysis = build_analysis(logs, mistakes, questions)
    if st.button("分析を更新"):
        st.rerun()

    st.write(analysis["summary"])
    st.write(f"次の学習提案: {analysis['next_action']}")

    with st.container(border=True):
        st.write("弱点率")
        for key, value in analysis["weak_rates"].items():
            st.write(f"- {key}: {value}%")

    with st.container(border=True):
        st.write("ミス分類ランキング")
        for key, value in analysis["mistake_ranking"].items():
            st.write(f"- {key}: {value}")

    with st.container(border=True):
        st.write("苦手ランキング")
        for key, value in analysis["weakness_ranking"].items():
            st.write(f"- {key}: {value}")

    with st.container(border=True):
        st.write("おすすめの次の難易度")
        st.write(f"- {analysis['recommended_difficulty']}")
        st.write("- 正答率と最近の流れから自動で提案しています。")

    st.subheader("類題生成")
    recommended_focus = analysis["top_weakness"] or "定義域見落とし"
    if st.button(f"{recommended_focus} 向けに 3 問生成する"):
        generated = generate_question_batch(3, "自動調整", "定義域あり", recommended_focus, questions)
        existing = load_json(QUESTIONS_FILE)
        existing.extend(generated)
        save_json(QUESTIONS_FILE, existing)
        st.success("類題を追加しました。『解答』タブから解けます。")
        st.rerun()

    if analysis["due_reviews"]:
        st.subheader("復習期限が来た問題")
        for item in analysis["due_reviews"][:3]:
            with st.container(border=True):
                st.write(item["prompt"])
                st.caption(f"{item['difficulty']} / 前回結果: {item.get('last_result') or '未解答'}")

    render_video_recommendations(analysis)


def main() -> None:
    init_page()

    logs = load_json(LOGS_FILE)
    mistakes = load_json(MISTAKES_FILE)
    questions = load_json(QUESTIONS_FILE)
    analysis = build_analysis(logs, mistakes, questions)

    st.title(APP_TITLE)
    st.caption("問題生成 → 解答 → ミス分析 → 類題生成 → 自動改善 を回す、スマホ向け学習改善アプリ")
    render_storage_status()
    st.caption("スマホではブラウザの『ホーム画面に追加』を使うと、アプリのように開きやすくなります。")

    tabs = st.tabs(["ホーム", "問題生成", "解答", "分析"])
    with tabs[0]:
        render_home(logs, mistakes, questions, analysis)
    with tabs[1]:
        render_problem_tab(logs, mistakes, questions, analysis)
    with tabs[2]:
        render_answer_tab()
    with tabs[3]:
        render_analysis_tab(logs, mistakes, questions)


if __name__ == "__main__":
    main()
