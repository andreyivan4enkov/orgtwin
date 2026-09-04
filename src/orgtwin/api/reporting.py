"""Отчёты директору и сценарии сравнения."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
SCENARIO_DIR = ROOT / "data" / "derived" / "scenarios"
ARENA_DIR = ROOT / "data" / "derived" / "arena"


def save_scenario(donor_id: str, name: str, payload: dict[str, Any]) -> dict:
    SCENARIO_DIR.mkdir(parents=True, exist_ok=True)
    path = SCENARIO_DIR / f"{donor_id}__{name}.json"
    data = {"donor_id": donor_id, "name": name, **payload}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return data


def load_scenario(donor_id: str, name: str) -> dict | None:
    path = SCENARIO_DIR / f"{donor_id}__{name}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def list_scenarios(donor_id: str) -> list[str]:
    SCENARIO_DIR.mkdir(parents=True, exist_ok=True)
    out = []
    for p in SCENARIO_DIR.glob(f"{donor_id}__*.json"):
        out.append(p.stem.split("__", 1)[-1])
    return sorted(out)


def compare_scenarios(a: dict, b: dict) -> dict[str, Any]:
    def peak(s: dict) -> float | None:
        q = s.get("queue") or s.get("scenario") or s.get("baseline") or {}
        return q.get("max_queue_any_real")

    return {
        "a_name": a.get("name"),
        "b_name": b.get("name"),
        "peak_a": peak(a),
        "peak_b": peak(b),
        "delta_peak": (peak(b) or 0) - (peak(a) or 0),
        "metrics_a": a.get("metrics"),
        "metrics_b": b.get("metrics"),
    }


def render_director_html(model: dict, *, whatif: dict | None = None, compare: dict | None = None) -> str:
    m = model.get("metrics") or {}
    q = model.get("queue_slices") or {}
    x1 = q.get("x1") or {}
    x2 = q.get("x2") or {}
    proven = (model.get("honesty") or {}).get("proven") or []
    not_p = (model.get("honesty") or {}).get("not_proven") or []
    agents = model.get("agents") or []
    hot = sorted(agents, key=lambda a: -(a.get("stuck_frac") or 0))[:5]

    def pct(x):
        return "—" if x is None else f"{100 * float(x):.1f}%"

    whatif_block = ""
    if whatif:
        whatif_block = f"""
        <h2>Что если</h2>
        <p>Δ max_queue: <b>{whatif.get('delta_max_queue')}</b>
        (было {whatif.get('baseline', {}).get('max_queue_any_real')},
        стало {whatif.get('scenario', {}).get('max_queue_any_real')})</p>
        """
    compare_block = ""
    if compare:
        compare_block = f"""
        <h2>Сравнение сценариев</h2>
        <p>{compare.get('a_name')} → {compare.get('b_name')}:
        peak {compare.get('peak_a')} → {compare.get('peak_b')}
        (Δ {compare.get('delta_peak')})</p>
        """

    hot_rows = "".join(
        f"<li>{a.get('id')} — застревание {pct(a.get('stuck_frac'))}</li>" for a in hot
    )
    return f"""<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8"/>
<title>OrgTwin — отчёт {model.get('donor_id')}</title>
<style>
body{{font-family:system-ui,sans-serif;max-width:820px;margin:32px auto;color:#111;}}
h1{{font-size:22px}} h2{{font-size:16px;margin-top:28px}}
.muted{{color:#555}} .box{{border:1px solid #ddd;padding:12px 16px;border-radius:8px}}
@media print {{ body {{ margin: 12mm }} }}
</style></head><body>
<h1>OrgTwin — отчёт для директора</h1>
<p class="muted">{model.get('label')} · {model.get('donor_id')}</p>
<div class="box">
<p><b>Решение:</b> смотреть узкие места очереди и незаменимых сотрудников до найма/перестройки.</p>
<p><b>Риск:</b> без своего лога и смен метрики — оценка по публичному/загруженному следу.</p>
<p><b>Следующий шаг:</b> сценарий «что если» → зафиксировать baseline/after → пилот на данных клиента.</p>
</div>
<h2>Предсказание следующего шага</h2>
<p>Топ-1: <b>{pct(m.get('next_step'))}</b> · Топ-3: <b>{pct(m.get('top3'))}</b>
· n={m.get('n')} · {m.get('policy_kind') or ''}</p>
<p class="muted">Σdt / длительность кейса — оценка очереди DES, не календарный wall-clock ERP.</p>
<h2>Нагрузка</h2>
<p>×1 max_queue={x1.get('max_queue_any_real')} (затор: {x1.get('bottleneck_agent')})<br/>
×2 max_queue={x2.get('max_queue_any_real')} (затор: {x2.get('bottleneck_agent')})</p>
<h2>Топ проблемных</h2>
<ul>{hot_rows or '<li class="muted">нет данных</li>'}</ul>
{whatif_block}
{compare_block}
<h2>Что доказано</h2>
<ul>{''.join(f'<li>{x}</li>' for x in proven)}</ul>
<h2>Что ещё не доказано</h2>
<ul>{''.join(f'<li>{x}</li>' for x in not_p)}</ul>
</body></html>"""


def save_arena_attempt(payload: dict) -> dict:
    ARENA_DIR.mkdir(parents=True, exist_ok=True)
    n = len(list(ARENA_DIR.glob("attempt_*.json"))) + 1
    path = ARENA_DIR / f"attempt_{n:04d}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    payload = {**payload, "id": path.stem}
    return payload


def arena_passed(peak_after: float, threshold: float = 5.0) -> bool:
    return float(peak_after) <= float(threshold)
