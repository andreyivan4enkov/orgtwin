"""
Два независимых контура OrgTwin.

Диагност — продукт (правила агента, застревание, holdout next-step).
Симулятор — исследование (FEP, timing, batch-sim, нагрузка) — не критический путь.
"""

from __future__ import annotations

from pathlib import Path

CONTOUR_DIAGNOSTIC = "diagnostic"
CONTOUR_SIMULATOR = "simulator"

RECIPE_DIAGNOSTIC = "agent_rules"
RECIPE_SIMULATOR = "softmax_fep_ab"

CONTOUR_RECIPES: dict[str, frozenset[str]] = {
    CONTOUR_DIAGNOSTIC: frozenset({RECIPE_DIAGNOSTIC}),
    CONTOUR_SIMULATOR: frozenset({RECIPE_SIMULATOR}),
}


def infer_contour(recipe: dict) -> str:
    c = recipe.get("contour")
    if c in CONTOUR_RECIPES:
        return str(c)
    recipe_name = recipe.get("recipe", RECIPE_SIMULATOR)
    if recipe_name == RECIPE_DIAGNOSTIC:
        return CONTOUR_DIAGNOSTIC
    return CONTOUR_SIMULATOR


def validate_contour_recipe(recipe: dict, expected: str | None = None) -> str:
    contour = infer_contour(recipe)
    recipe_name = recipe.get("recipe", "")
    allowed = CONTOUR_RECIPES.get(contour, frozenset())
    if recipe_name not in allowed:
        raise SystemExit(
            f"Контур «{contour}» не поддерживает recipe={recipe_name!r}. "
            f"Допустимо: {sorted(allowed)}"
        )
    if expected is not None and contour != expected:
        raise SystemExit(
            f"Конфиг для контура «{contour}», ожидался «{expected}». "
            f"Проверьте поле contour и путь configs/{{diagnostic|simulator}}/"
        )
    return contour


def reports_root(root: Path, contour: str) -> Path:
    return root / "reports" / contour


def derived_root(root: Path, contour: str) -> Path:
    return root / "data" / "derived" / contour


def journal_path(root: Path, contour: str) -> Path:
    name = "LAB_JOURNAL.md" if contour == CONTOUR_DIAGNOSTIC else "SIMULATOR_JOURNAL.md"
    return root / "reports" / contour / name
