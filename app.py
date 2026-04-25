from __future__ import annotations

import base64
import json
import math
import random
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

import requests
import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError


APP_TITLE = "数学I・A・II・B 学習最適化"
DATA_DIR = Path("data")
LOGS_FILE = DATA_DIR / "logs.json"
MISTAKES_FILE = DATA_DIR / "mistakes.json"
QUESTIONS_FILE = DATA_DIR / "questions.json"

GITHUB_API_BASE = "https://api.github.com"
DIFFICULTIES = ["自動調整", "基礎", "標準", "共通テスト風"]
REVIEW_INTERVALS_CORRECT = [1, 3, 7]
REVIEW_INTERVALS_INCORRECT = [0, 1, 3]
REFLECTION_STEPS = ["条件整理", "公式選択", "計算処理", "図形イメージ", "場合分け", "見直し"]

MATH_CURRICULUM: dict[str, dict[str, dict[str, Any]]] = {
    "数学I": {
        "二次関数": {
            "concepts": ["軸と頂点", "最大最小", "定義域つきの判定"],
            "skills": ["軸ミス", "定義域見落とし", "端点比較忘れ"],
            "videos": [
                ("二次関数の最大・最小", "https://www.youtube.com/watch?v=QrXZgYOSZ4w"),
                ("二次関数の最大・最小 演習", "https://youtu.be/hjsJ12VWFDs"),
            ],
        },
        "図形と計量": {
            "concepts": ["正弦定理", "余弦定理", "面積公式"],
            "skills": ["公式選択ミス", "図の読み違い", "条件整理不足"],
            "videos": [("図形と計量の基本", "https://www.youtube.com/results?search_query=%E5%9B%B3%E5%BD%A2%E3%81%A8%E8%A8%88%E9%87%8F+%E6%AD%A3%E5%BC%A6%E5%AE%9A%E7%90%86")],
        },
        "三角比": {
            "concepts": ["基本値", "相互関係", "鈍角への拡張"],
            "skills": ["値の暗記不足", "符号ミス", "相互関係の使い忘れ"],
            "videos": [("三角比の基本", "https://www.youtube.com/results?search_query=%E4%B8%89%E8%A7%92%E6%AF%94+%E5%9F%BA%E6%9C%AC")],
        },
    },
    "数学A": {
        "場合の数": {
            "concepts": ["順列", "組合せ", "重複の除去"],
            "skills": ["順列組合せの混同", "数え漏れ", "重複カウント"],
            "videos": [("場合の数の基本", "https://www.youtube.com/results?search_query=%E5%A0%B4%E5%90%88%E3%81%AE%E6%95%B0+%E9%A0%86%E5%88%97+%E7%B5%84%E5%90%88%E3%81%9B")],
        },
        "確率": {
            "concepts": ["余事象", "独立試行", "条件つき確率の前段階"],
            "skills": ["全事象の取り違え", "余事象の使い忘れ", "樹形図不足"],
            "videos": [("確率の基本", "https://www.youtube.com/results?search_query=%E7%A2%BA%E7%8E%87+%E4%BD%99%E4%BA%8B%E8%B1%A1+%E7%8B%AC%E7%AB%8B%E8%A9%A6%E8%A1%8C")],
        },
    },
    "数学II": {
        "指数・対数": {
            "concepts": ["指数法則", "対数の性質", "簡単な方程式"],
            "skills": ["底の変換ミス", "対数法則の混同", "定義域見落とし"],
            "videos": [("指数対数の基本", "https://www.youtube.com/results?search_query=%E6%8C%87%E6%95%B0+%E5%AF%BE%E6%95%B0+%E5%9F%BA%E6%9C%AC")],
        },
        "微分法": {
            "concepts": ["導関数", "接線", "増減と極値"],
            "skills": ["微分計算ミス", "符号判定ミス", "接線式の立て方ミス"],
            "videos": [("微分法の基本", "https://www.youtube.com/results?search_query=%E5%BE%AE%E5%88%86%E6%B3%95+%E5%A2%97%E6%B8%9B+%E6%8E%A5%E7%B7%9A")],
        },
    },
    "数学B": {
        "数列": {
            "concepts": ["等差数列", "等比数列", "和の計算"],
            "skills": ["一般項ミス", "和の公式ミス", "初項公差の取り違え"],
            "videos": [("数列の基本", "https://www.youtube.com/results?search_query=%E6%95%B0%E5%88%97+%E7%AD%89%E5%B7%AE+%E7%AD%89%E6%AF%94")],
        },
        "ベクトル": {
            "concepts": ["成分計算", "内積", "位置ベクトル"],
            "skills": ["符号ミス", "座標変換ミス", "図形条件の翻訳不足"],
            "videos": [("ベクトルの基本", "https://www.youtube.com/results?search_query=%E3%83%99%E3%82%AF%E3%83%88%E3%83%AB+%E5%86%85%E7%A9%8D+%E5%9F%BA%E6%9C%AC")],
        },
    },
}


@dataclass
class QuestionBundle:
    record: dict[str, Any]


def ensure_data_files() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    for path in [LOGS_FILE, MISTAKES_FILE, QUESTIONS_FILE]:
        if not path.exists():
            path.write_text("[]", encoding="utf-8")


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
    return dt is not None and dt <= now_dt()


def next_review_iso(review_level: int, correct: bool) -> str:
    ladder = REVIEW_INTERVALS_CORRECT if correct else REVIEW_INTERVALS_INCORRECT
    level = max(0, min(review_level, len(ladder) - 1))
    days = ladder[level]
    when = now_dt() + timedelta(days=days)
    if not correct and days == 0:
        when = now_dt() + timedelta(minutes=20)
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
        return json.loads(content), payload["sha"]
    except json.JSONDecodeError:
        return [], payload["sha"]


def github_save_file(path: Path, data: list[dict[str, Any]]) -> None:
    _, sha = github_fetch_file(path)
    url = f"{GITHUB_API_BASE}/repos/{secret('GITHUB_REPO')}/contents/{repo_relative_path(path)}"
    body: dict[str, Any] = {
        "message": f"Update {repo_relative_path(path)} from Streamlit app",
        "content": base64.b64encode(json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")).decode("utf-8"),
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
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def save_json(path: Path, data: list[dict[str, Any]]) -> None:
    ensure_data_files()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    if github_storage_enabled():
        try:
            github_save_file(path, data)
        except requests.RequestException:
            st.error("GitHub への永続保存に失敗しました。トークンやリポジトリ設定を確認してください。")


def append_json(path: Path, item: dict[str, Any]) -> None:
    data = load_json(path)
    data.append(item)
    save_json(path, data)


def count_by_key(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = item.get(key)
        if not value:
            continue
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: kv[1], reverse=True))


def today_minutes(logs: list[dict[str, Any]]) -> int:
    today_text = str(date.today())
    return sum(int(item.get("study_minutes", 0)) for item in logs if item.get("date") == today_text)


def recommended_difficulty(questions: list[dict[str, Any]]) -> str:
    recent = [q for q in sorted(questions, key=lambda x: x["created_at"], reverse=True) if q.get("answered")][:8]
    if not recent:
        return "基礎"
    ratio = sum(1 for q in recent if q.get("last_result") == "correct") / len(recent)
    if ratio >= 0.8 and len(recent) >= 5:
        if any(q["difficulty"] == "標準" for q in recent):
            return "共通テスト風"
        return "標準"
    if ratio <= 0.45:
        return "基礎"
    return "標準"


def shuffle_choices(rng: random.Random, options: list[str], correct_index: int) -> tuple[list[str], int]:
    pairs = list(enumerate(options))
    rng.shuffle(pairs)
    shuffled = [text for _, text in pairs]
    new_correct = next(i for i, (old_i, _) in enumerate(pairs) if old_i == correct_index)
    return shuffled, new_correct


def make_question_record(
    *,
    course: str,
    unit: str,
    concept: str,
    difficulty: str,
    skill_tag: str,
    prompt: str,
    choices: list[str],
    correct_index: int,
    answer_text: str,
    explanation: dict[str, Any],
    source: str = "curated",
) -> QuestionBundle:
    return QuestionBundle(
        record={
            "id": str(uuid.uuid4()),
            "created_at": now_iso(),
            "subject": "数学",
            "course": course,
            "unit": unit,
            "concept": concept,
            "difficulty": difficulty,
            "skill_tag": skill_tag,
            "prompt": prompt,
            "choices": choices,
            "correct_index": correct_index,
            "answer_text": answer_text,
            "explanation": explanation,
            "answered": False,
            "last_result": None,
            "last_choice": None,
            "favorite": False,
            "hold": False,
            "review_level": 0,
            "review_count": 0,
            "next_review_at": None,
            "reflection_history": [],
            "source": source,
        }
    )


def explain_block(type_text: str, overview: str, steps: list[str], pitfalls: list[str], rule: str) -> dict[str, Any]:
    return {
        "type": type_text,
        "overview": overview,
        "steps": steps,
        "pitfalls": pitfalls,
        "rule": rule,
    }


def gen_quadratic(rng: random.Random, difficulty: str) -> QuestionBundle:
    a = rng.choice([1, -1, 2, -2, 3, -3] if difficulty != "基礎" else [1, -1, 2, -2])
    h = rng.randint(-4, 4)
    k = rng.randint(-6, 6)
    left = h + rng.choice([-4, -3, -2, 2, 3, 4])
    right = left + rng.randint(2, 5)
    if left > right:
        left, right = right, left
    axis_inside = left <= h <= right
    y_h = a * (h - h) ** 2 + k
    y_l = a * (left - h) ** 2 + k
    y_r = a * (right - h) ** 2 + k
    max_value = max(y_h if axis_inside else -10**9, y_l, y_r) if axis_inside else max(y_l, y_r)
    min_value = min(y_h if axis_inside else 10**9, y_l, y_r) if axis_inside else min(y_l, y_r)
    prompt = f"関数 f(x) = {a}(x - {h})^2 + {k} について、{left} <= x <= {right} における最小値として正しいものを選べ。"
    correct = min_value
    distractors = sorted({correct + d for d in [-6, -3, 3, 6] if correct + d != correct})
    options = [str(correct)] + [str(x) for x in distractors[:3]]
    options, correct_index = shuffle_choices(rng, options, 0)
    return make_question_record(
        course="数学I",
        unit="二次関数",
        concept="最大最小",
        difficulty=difficulty,
        skill_tag="定義域見落とし" if not axis_inside else "軸ミス",
        prompt=prompt,
        choices=options,
        correct_index=correct_index,
        answer_text=str(correct),
        explanation=explain_block(
            "定義域つき二次関数の最小値",
            "軸が範囲内か外かを先に判定し、比べるべき点を決める。",
            [
                f"軸は x = {h}。",
                f"定義域は {left} <= x <= {right} で、軸は {'範囲内' if axis_inside else '範囲外'}。",
                f"候補点の y 値を比べると最小値は {correct}。",
            ],
            ["定義域を見ずに頂点の値をそのまま答える。", "端点を片方しか計算しない。"],
            "二次関数は『軸確認 -> 範囲判定 -> 候補比較』の順で処理する。",
        ),
    )


def gen_trig(rng: random.Random, difficulty: str) -> QuestionBundle:
    angle = rng.choice([30, 45, 60, 120, 135, 150] if difficulty != "基礎" else [30, 45, 60])
    func = rng.choice(["sin", "cos", "tan"])
    values = {
        ("sin", 30): "1/2",
        ("sin", 45): "√2/2",
        ("sin", 60): "√3/2",
        ("sin", 120): "√3/2",
        ("sin", 135): "√2/2",
        ("sin", 150): "1/2",
        ("cos", 30): "√3/2",
        ("cos", 45): "√2/2",
        ("cos", 60): "1/2",
        ("cos", 120): "-1/2",
        ("cos", 135): "-√2/2",
        ("cos", 150): "-√3/2",
        ("tan", 30): "√3/3",
        ("tan", 45): "1",
        ("tan", 60): "√3",
        ("tan", 120): "-√3",
        ("tan", 135): "-1",
        ("tan", 150): "-√3/3",
    }
    correct = values[(func, angle)]
    wrong_pool = ["1/2", "√2/2", "√3/2", "1", "√3", "√3/3", "-1/2", "-√2/2", "-√3/2", "-1", "-√3", "-√3/3"]
    options = [correct] + [v for v in wrong_pool if v != correct][:3]
    options, correct_index = shuffle_choices(rng, options, 0)
    return make_question_record(
        course="数学I",
        unit="三角比",
        concept="基本値",
        difficulty=difficulty,
        skill_tag="値の暗記不足" if angle <= 60 else "符号ミス",
        prompt=f"{func}{angle}° の値として正しいものを選べ。",
        choices=options,
        correct_index=correct_index,
        answer_text=correct,
        explanation=explain_block(
            "三角比の基本値",
            "基準角の値と象限による符号を組み合わせて判断する。",
            [
                f"{angle}° の基準角を考える。",
                f"{func} の基本値を取り出す。",
                "鈍角なら符号を確認する。",
            ],
            ["45° と 60° の値を混同する。", "鈍角で符号を反転し忘れる。"],
            "三角比は『基本値 + 象限の符号』で処理する。",
        ),
    )


def gen_counting(rng: random.Random, difficulty: str) -> QuestionBundle:
    n = rng.randint(5, 8)
    r = rng.randint(2, min(4, n - 1))
    mode = rng.choice(["順列", "組合せ"])
    correct = math.perm(n, r) if mode == "順列" else math.comb(n, r)
    wrongs = []
    alt = math.comb(n, r) if mode == "順列" else math.perm(n, r)
    wrongs.append(alt)
    wrongs.append(correct + rng.randint(2, 8))
    wrongs.append(max(1, correct - rng.randint(1, 6)))
    options = [str(correct)] + [str(x) for x in wrongs[:3]]
    options, correct_index = shuffle_choices(rng, options, 0)
    return make_question_record(
        course="数学A",
        unit="場合の数",
        concept=mode,
        difficulty=difficulty,
        skill_tag="順列組合せの混同",
        prompt=f"{n} 人から {r} 人を {'並べて選ぶ' if mode == '順列' else '選ぶ'} 方法は何通りか。",
        choices=options,
        correct_index=correct_index,
        answer_text=str(correct),
        explanation=explain_block(
            f"{mode} の判定",
            "並べるかどうかを最初に決める。",
            [
                f"『{'順番がある' if mode == '順列' else '順番がない'}』ので {mode} を使う。",
                f"計算すると {correct} 通り。",
            ],
            ["順列と組合せを逆にする。", "意味を見ずに公式だけ選ぶ。"],
            "場合の数は『順序があるか』を最初に判定する。",
        ),
    )


def gen_probability(rng: random.Random, difficulty: str) -> QuestionBundle:
    red = rng.randint(2, 5)
    blue = rng.randint(2, 5)
    total = red + blue
    correct = f"{blue}/{total}" if rng.choice([True, False]) else f"{red}/{total}"
    target = "青玉" if correct.startswith(str(blue)) else "赤玉"
    wrongs = [f"{red}/{total}" if target == "青玉" else f"{blue}/{total}", f"1/{total}", f"{abs(red-blue)}/{total}"]
    options = [correct] + wrongs[:3]
    options, correct_index = shuffle_choices(rng, options, 0)
    return make_question_record(
        course="数学A",
        unit="確率",
        concept="基本確率",
        difficulty=difficulty,
        skill_tag="全事象の取り違え",
        prompt=f"赤玉 {red} 個、青玉 {blue} 個が入った袋から 1 個取り出す。{target}が出る確率として正しいものを選べ。",
        choices=options,
        correct_index=correct_index,
        answer_text=correct,
        explanation=explain_block(
            "基本確率",
            "求める確率は『有利な場合 / 全体の場合』で考える。",
            [f"全体は {total} 通り。", f"{target} が出る有利な場合は {blue if target == '青玉' else red} 通り。", f"よって {correct}。"],
            ["分母を有利な場合にしてしまう。", "余事象と混同する。"],
            "確率は『有利 / 全体』を毎回言葉で確認する。",
        ),
    )


def gen_logarithm(rng: random.Random, difficulty: str) -> QuestionBundle:
    a = rng.choice([2, 3, 4, 5])
    b = rng.choice([8, 9, 16, 25, 27, 32])
    value_map = {(2, 8): "3", (2, 16): "4", (2, 32): "5", (3, 9): "2", (3, 27): "3", (4, 16): "2", (5, 25): "2"}
    if (a, b) not in value_map:
        a, b = 2, 8
    correct = value_map[(a, b)]
    options = [correct, "1", "2", "4"]
    options, correct_index = shuffle_choices(rng, options, 0)
    return make_question_record(
        course="数学II",
        unit="指数・対数",
        concept="対数の性質",
        difficulty=difficulty,
        skill_tag="対数法則の混同",
        prompt=f"log_{a} {b} の値として正しいものを選べ。",
        choices=options,
        correct_index=correct_index,
        answer_text=correct,
        explanation=explain_block(
            "対数の定義",
            "a^x = b を満たす x を考える。",
            [f"{a}^x = {b} を考える。", f"x = {correct} なので log_{a} {b} = {correct}。"],
            ["底と真数を逆に読む。", "対数法則を使う前に定義へ戻らない。"],
            "対数で迷ったら、まず指数の形へ戻す。",
        ),
    )


def gen_calculus(rng: random.Random, difficulty: str) -> QuestionBundle:
    a = rng.choice([1, 2, 3])
    b = rng.randint(-4, 4)
    c = rng.randint(-3, 3)
    x0 = rng.randint(-2, 3)
    slope = 2 * a * x0 + b
    options = [str(slope), str(slope + 2), str(slope - 2), str(-slope)]
    options, correct_index = shuffle_choices(rng, options, 0)
    return make_question_record(
        course="数学II",
        unit="微分法",
        concept="接線の傾き",
        difficulty=difficulty,
        skill_tag="微分計算ミス",
        prompt=f"f(x) = {a}x^2 + {b}x + {c} の x = {x0} における接線の傾きとして正しいものを選べ。",
        choices=options,
        correct_index=correct_index,
        answer_text=str(slope),
        explanation=explain_block(
            "導関数の値",
            "接線の傾きは f'(x) の値で求める。",
            [f"f'(x) = {2 * a}x + {b}", f"x = {x0} を代入すると {slope}。"],
            ["微分後に代入し忘れる。", "係数2aを落とす。"],
            "接線の傾きは『微分してから代入』を徹底する。",
        ),
    )


def gen_sequence(rng: random.Random, difficulty: str) -> QuestionBundle:
    first = rng.randint(1, 6)
    diff = rng.randint(1, 5)
    n = rng.randint(5, 12)
    correct = first + (n - 1) * diff
    options = [str(correct), str(first + n * diff), str(first + (n - 2) * diff), str(first * n)]
    options, correct_index = shuffle_choices(rng, options, 0)
    return make_question_record(
        course="数学B",
        unit="数列",
        concept="等差数列",
        difficulty=difficulty,
        skill_tag="一般項ミス",
        prompt=f"初項 {first}、公差 {diff} の等差数列の第 {n} 項として正しいものを選べ。",
        choices=options,
        correct_index=correct_index,
        answer_text=str(correct),
        explanation=explain_block(
            "等差数列の一般項",
            "a_n = a_1 + (n-1)d を使う。",
            [f"a_{n} = {first} + ({n}-1)×{diff}", f"計算して {correct}。"],
            ["n-1 を n にしてしまう。", "初項を掛けてしまう。"],
            "等差数列は『初項 + (n-1)公差』で固定する。",
        ),
    )


def gen_vector(rng: random.Random, difficulty: str) -> QuestionBundle:
    ax, ay = rng.randint(-3, 4), rng.randint(-3, 4)
    bx, by = rng.randint(-3, 4), rng.randint(-3, 4)
    correct = ax * bx + ay * by
    options = [str(correct), str(ax + bx + ay + by), str(ax * bx - ay * by), str(abs(correct) + 2)]
    options, correct_index = shuffle_choices(rng, options, 0)
    return make_question_record(
        course="数学B",
        unit="ベクトル",
        concept="内積",
        difficulty=difficulty,
        skill_tag="符号ミス",
        prompt=f"a=({ax}, {ay}), b=({bx}, {by}) のとき、a・b として正しいものを選べ。",
        choices=options,
        correct_index=correct_index,
        answer_text=str(correct),
        explanation=explain_block(
            "ベクトルの内積",
            "成分ごとの積を足す。",
            [f"a・b = {ax}×{bx} + {ay}×{by}", f"計算して {correct}。"],
            ["足し算だけしてしまう。", "符号を落とす。"],
            "内積は『対応成分を掛けて足す』を固定する。",
        ),
    )


GENERATOR_MAP: dict[tuple[str, str], Callable[[random.Random, str], QuestionBundle]] = {
    ("数学I", "二次関数"): gen_quadratic,
    ("数学I", "三角比"): gen_trig,
    ("数学A", "場合の数"): gen_counting,
    ("数学A", "確率"): gen_probability,
    ("数学II", "指数・対数"): gen_logarithm,
    ("数学II", "微分法"): gen_calculus,
    ("数学B", "数列"): gen_sequence,
    ("数学B", "ベクトル"): gen_vector,
}


def available_courses() -> list[str]:
    return list(MATH_CURRICULUM.keys())


def available_units(course: str) -> list[str]:
    return list(MATH_CURRICULUM[course].keys())


def generate_questions(course: str, unit: str, difficulty: str, count: int, existing_questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actual_difficulty = recommended_difficulty(existing_questions) if difficulty == "自動調整" else difficulty
    generator = GENERATOR_MAP[(course, unit)]
    rng = random.Random()
    return [generator(rng, actual_difficulty).record for _ in range(count)]


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


def evaluate_multiple_choice(question: dict[str, Any], selected_index: int) -> tuple[bool, str]:
    correct = selected_index == int(question["correct_index"])
    if correct:
        return True, f"正解です。正答は {question['answer_text']} です。"
    return False, f"今回は不正解です。正答は {question['answer_text']} です。"


def apply_answer_result(question: dict[str, Any], correct: bool, selected_index: int) -> dict[str, Any]:
    current_level = int(question.get("review_level", 0))
    new_level = min(current_level + 1, len(REVIEW_INTERVALS_CORRECT) - 1) if correct else 0
    question["answered"] = True
    question["last_result"] = "correct" if correct else "incorrect"
    question["last_choice"] = selected_index
    question["answered_at"] = now_iso()
    question["review_level"] = new_level
    question["review_count"] = int(question.get("review_count", 0)) + 1
    question["next_review_at"] = next_review_iso(new_level, correct)
    if correct:
        question["hold"] = False
    return question


def build_mistake(question: dict[str, Any], selected_index: int) -> dict[str, Any]:
    chosen = question["choices"][selected_index]
    return {
        "id": str(uuid.uuid4()),
        "created_at": now_iso(),
        "question_id": question["id"],
        "course": question["course"],
        "unit": question["unit"],
        "concept": question["concept"],
        "difficulty": question["difficulty"],
        "problem": question["prompt"],
        "my_answer": chosen,
        "correct_answer": question["answer_text"],
        "mistake_category": "選択式の誤答",
        "skill_tag": question["skill_tag"],
    }


def save_reflection(question_id: str, reflection: dict[str, Any]) -> None:
    questions = load_json(QUESTIONS_FILE)
    for item in questions:
        if item["id"] == question_id:
            history = item.get("reflection_history", [])
            history.append(reflection)
            item["reflection_history"] = history
            break
    save_json(QUESTIONS_FILE, questions)


def compute_accuracy(questions: list[dict[str, Any]]) -> float:
    answered = [q for q in questions if q.get("answered")]
    if not answered:
        return 0.0
    return sum(1 for q in answered if q.get("last_result") == "correct") / len(answered)


def build_reflection_insight(questions: list[dict[str, Any]]) -> str:
    reflections = []
    for q in questions:
        reflections.extend(q.get("reflection_history", []))
    if not reflections:
        return "振り返りデータはまだ少なめです。解いたあとに任意の質問へ答えると分析が深くなります。"
    step_counts = count_by_key(reflections, "hardest_step")
    top = next(iter(step_counts), "")
    avg = sum(int(r.get("confidence", 0)) for r in reflections) / len(reflections)
    return f"振り返りでは『{top}』で詰まりやすい傾向です。平均自信度は {avg:.1f}/5 です。"


def select_videos(course: str, unit: str) -> list[tuple[str, str]]:
    return MATH_CURRICULUM[course][unit]["videos"]


def build_analysis(logs: list[dict[str, Any]], mistakes: list[dict[str, Any]], questions: list[dict[str, Any]]) -> dict[str, Any]:
    accuracy = compute_accuracy(questions)
    due_reviews = [q for q in questions if is_due(q.get("next_review_at"))]
    unit_ranking = count_by_key(mistakes, "unit")
    skill_ranking = count_by_key(mistakes, "skill_tag")
    course_ranking = count_by_key(mistakes, "course")
    favorites = [q for q in questions if q.get("favorite")]
    holds = [q for q in questions if q.get("hold")]
    top_unit = next(iter(unit_ranking), None)
    top_skill = next(iter(skill_ranking), None)
    suggestion = "まずは基礎難度で 5 問ほど解いてデータをためる。"
    if top_unit and top_skill:
        suggestion = f"{top_unit} の {top_skill} が弱点です。次はその単元に絞って 5 問解きましょう。"
    return {
        "today_minutes": today_minutes(logs),
        "accuracy": accuracy,
        "due_reviews": due_reviews,
        "unit_ranking": unit_ranking,
        "skill_ranking": skill_ranking,
        "course_ranking": course_ranking,
        "favorites": favorites,
        "holds": holds,
        "recommended_difficulty": recommended_difficulty(questions),
        "reflection_insight": build_reflection_insight(questions),
        "suggestion": suggestion,
        "top_unit": top_unit,
        "top_skill": top_skill,
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
                radial-gradient(circle at top right, rgba(22,101,52,0.10), transparent 28%),
                linear-gradient(180deg, #faf7ef 0%, #eef6ff 100%);
        }
        .block-container {
            max-width: 780px;
            padding-top: 1rem;
            padding-bottom: 4rem;
        }
        @media (max-width: 640px) {
            .block-container {
                padding-left: 0.8rem;
                padding-right: 0.8rem;
                padding-top: 0.6rem;
            }
            .stTabs [data-baseweb="tab"] {
                height: 3rem;
                white-space: nowrap;
            }
        }
        .stButton > button, div[data-baseweb="button"] > button {
            width: 100%;
            min-height: 3rem;
            border-radius: 16px;
            font-weight: 700;
            border: none;
            background: #166534;
            color: white;
        }
        .stRadio label {
            line-height: 1.35;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def init_page() -> None:
    st.set_page_config(page_title=APP_TITLE, page_icon="📗", layout="centered")
    app_css()
    ensure_data_files()


def render_storage_status() -> None:
    if github_storage_enabled():
        st.success(f"保存モード: GitHub 永続保存 ({secret('GITHUB_REPO')} / {github_branch()})")
    else:
        st.warning("保存モード: 一時ファイル。永続化するには Streamlit secrets に GitHub 設定を追加してください。")


def render_home(logs: list[dict[str, Any]], questions: list[dict[str, Any]], analysis: dict[str, Any]) -> None:
    st.subheader("今日の状況")
    c1, c2 = st.columns(2)
    with c1:
        render_metric_card("学習時間", f"{analysis['today_minutes']} 分")
    with c2:
        render_metric_card("正答率", f"{int(analysis['accuracy'] * 100)}%")
    c3, c4 = st.columns(2)
    with c3:
        render_metric_card("復習キュー", f"{len(analysis['due_reviews'])} 問")
    with c4:
        render_metric_card("次の難易度", analysis["recommended_difficulty"])
    render_metric_card("次にやること", analysis["suggestion"])
    render_metric_card("振り返り分析", analysis["reflection_insight"])

    with st.expander("学習ログを追加", expanded=False):
        with st.form("study_log_form", clear_on_submit=True):
            log_date = st.date_input("日付", value=date.today())
            course = st.selectbox("分野", available_courses())
            unit = st.selectbox("単元", available_units(course))
            study_minutes = st.number_input("学習時間（分）", min_value=0, max_value=600, value=30, step=10)
            focus = st.slider("集中度", 1, 5, 3)
            content = st.text_area("内容", placeholder="何を勉強したかを短く")
            submitted = st.form_submit_button("学習ログを保存")
            if submitted:
                append_json(
                    LOGS_FILE,
                    {
                        "id": str(uuid.uuid4()),
                        "created_at": now_iso(),
                        "date": str(log_date),
                        "subject": "数学",
                        "course": course,
                        "unit": unit,
                        "study_minutes": int(study_minutes),
                        "focus": focus,
                        "content": content,
                    },
                )
                st.success("学習ログを保存しました。")
                st.rerun()

    st.subheader("数学I・A・II・B の対応範囲")
    for course, units in MATH_CURRICULUM.items():
        with st.container(border=True):
            st.write(course)
            st.write("・" + " / ".join(units.keys()))

    st.subheader("最近の問題")
    recent = sorted(questions, key=lambda q: q["created_at"], reverse=True)[:4]
    if not recent:
        st.info("まだ問題がありません。『問題生成』タブから作成してください。")
    for q in recent:
        with st.container(border=True):
            st.write(q["prompt"])
            st.caption(f"{q['course']} / {q['unit']} / {q['difficulty']} / 分析軸: {q['skill_tag']}")


def render_problem_tab(questions: list[dict[str, Any]], analysis: dict[str, Any]) -> None:
    st.subheader("問題生成")
    course = st.selectbox("科目群", available_courses(), key="course_generate")
    unit = st.selectbox("単元", available_units(course), key="unit_generate")
    difficulty = st.selectbox("難易度", DIFFICULTIES, index=0)
    count = st.slider("問題数", 1, 10, 3)
    with st.form("generate_form"):
        submitted = st.form_submit_button("問題を生成する")
        if submitted:
            generated = generate_questions(course, unit, difficulty, count, questions)
            questions.extend(generated)
            save_json(QUESTIONS_FILE, questions)
            st.success(f"{course} / {unit} の問題を {count} 問追加しました。")
            st.rerun()

    if analysis["top_unit"] and analysis["top_unit"] in available_units(course):
        if st.button(f"弱点の {analysis['top_unit']} を 5 問追加する"):
            generated = generate_questions(course, analysis["top_unit"], "自動調整", 5, questions)
            questions.extend(generated)
            save_json(QUESTIONS_FILE, questions)
            st.success("弱点単元の問題を追加しました。")
            st.rerun()

    st.subheader("単元の解説動画")
    for title, url in select_videos(course, unit):
        st.write(f"- [{title}]({url})")

    st.subheader("最近の生成問題")
    latest = sorted(questions, key=lambda q: q["created_at"], reverse=True)[:6]
    for q in latest:
        with st.container(border=True):
            st.write(q["prompt"])
            for i, choice in enumerate(q["choices"]):
                st.write(f"{chr(65+i)}. {choice}")


def filter_question_pool(questions: list[dict[str, Any]], mode: str) -> list[dict[str, Any]]:
    ordered = sorted(questions, key=lambda q: q["created_at"], reverse=True)
    if mode == "復習期限だけ":
        return [q for q in ordered if is_due(q.get("next_review_at"))]
    if mode == "お気に入り":
        return [q for q in ordered if q.get("favorite")]
    if mode == "保留":
        return [q for q in ordered if q.get("hold")]
    return ordered


def render_question_actions(question: dict[str, Any]) -> None:
    c1, c2 = st.columns(2)
    with c1:
        if st.button("お気に入り" if not question.get("favorite") else "お気に入り解除", key=f"fav_{question['id']}"):
            toggle_question_flag(question["id"], "favorite")
            st.rerun()
    with c2:
        if st.button("あとで解く" if not question.get("hold") else "保留解除", key=f"hold_{question['id']}"):
            toggle_question_flag(question["id"], "hold")
            st.rerun()


def render_explanation(question: dict[str, Any]) -> None:
    exp = question["explanation"]
    st.write("問題の型")
    st.write(exp["type"])
    st.write("解法の全体像")
    st.write(exp["overview"])
    st.write("手順")
    for step in exp["steps"]:
        st.write(f"- {step}")
    st.write("よくあるミス")
    for item in exp["pitfalls"]:
        st.write(f"- {item}")
    st.write("一般化ルール")
    st.write(exp["rule"])


def render_reflection_form(question: dict[str, Any]) -> None:
    with st.expander("任意の振り返り質問", expanded=False):
        with st.form(f"reflection_{question['id']}", clear_on_submit=True):
            confidence = st.slider("今回はどれくらい自信がありましたか？", 1, 5, 3)
            hardest_step = st.selectbox("いちばん難しかった工程", ["特になし"] + REFLECTION_STEPS)
            memo = st.text_area("メモ", placeholder="次に気をつけたいこと")
            submitted = st.form_submit_button("振り返りを保存")
            if submitted:
                save_reflection(
                    question["id"],
                    {
                        "created_at": now_iso(),
                        "confidence": confidence,
                        "hardest_step": "" if hardest_step == "特になし" else hardest_step,
                        "memo": memo,
                    },
                )
                st.success("振り返りを保存しました。")
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
    labels = [f"{q['course']} | {q['unit']} | {q['prompt'][:24]}..." for q in pool]
    selected = st.selectbox("問題を選ぶ", labels)
    question = pool[labels.index(selected)]

    with st.container(border=True):
        st.write(question["prompt"])
        st.caption(f"{question['course']} / {question['unit']} / 分析軸: {question['skill_tag']}")
    render_question_actions(question)

    show_reflection = question.get("last_result") is not None
    choice = st.radio(
        "選択肢を選ぶ",
        options=list(range(len(question["choices"]))),
        format_func=lambda i: f"{chr(65+i)}. {question['choices'][i]}",
        key=f"choice_{question['id']}",
    )
    if st.button("判定する", key=f"submit_{question['id']}"):
        correct, feedback = evaluate_multiple_choice(question, int(choice))
        updated = apply_answer_result(question, correct, int(choice))
        update_question(updated)
        if not correct:
            append_json(MISTAKES_FILE, build_mistake(question, int(choice)))
        if correct:
            st.success(feedback)
        else:
            st.error(feedback)
        with st.expander("解説", expanded=True):
            render_explanation(question)
        show_reflection = True

    if show_reflection:
        render_reflection_form(question)


def render_analysis_tab(logs: list[dict[str, Any]], mistakes: list[dict[str, Any]], questions: list[dict[str, Any]]) -> None:
    st.subheader("分析")
    analysis = build_analysis(logs, mistakes, questions)
    if st.button("分析を更新"):
        st.rerun()
    st.write(analysis["suggestion"])
    with st.container(border=True):
        st.write("コース別ミスランキング")
        for key, value in analysis["course_ranking"].items():
            st.write(f"- {key}: {value}")
    with st.container(border=True):
        st.write("単元別ミスランキング")
        for key, value in analysis["unit_ranking"].items():
            st.write(f"- {key}: {value}")
    with st.container(border=True):
        st.write("技能別ランキング")
        for key, value in analysis["skill_ranking"].items():
            st.write(f"- {key}: {value}")
    with st.container(border=True):
        st.write("振り返り分析")
        st.write(analysis["reflection_insight"])
    if analysis["due_reviews"]:
        st.subheader("復習期限が来た問題")
        for q in analysis["due_reviews"][:4]:
            with st.container(border=True):
                st.write(q["prompt"])
                st.caption(f"{q['course']} / {q['unit']} / 前回結果: {q.get('last_result')}")


def main() -> None:
    init_page()
    logs = load_json(LOGS_FILE)
    mistakes = load_json(MISTAKES_FILE)
    questions = load_json(QUESTIONS_FILE)
    analysis = build_analysis(logs, mistakes, questions)

    st.title(APP_TITLE)
    st.caption("数学I・A・II・B 専用の、選択式ベース学習最適化アプリ")
    render_storage_status()
    st.caption("現在は数学専用です。記述式ではなく、スマホで解きやすい4択中心で構成しています。")

    tabs = st.tabs(["ホーム", "問題生成", "解答", "分析"])
    with tabs[0]:
        render_home(logs, questions, analysis)
    with tabs[1]:
        render_problem_tab(questions, analysis)
    with tabs[2]:
        render_answer_tab()
    with tabs[3]:
        render_analysis_tab(logs, mistakes, questions)


if __name__ == "__main__":
    main()
