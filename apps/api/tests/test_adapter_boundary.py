"""Architectural guard.

CLAUDE.md forbids domain code depending on a vendor SDK. That rule is only worth anything
if something enforces it, so this test is the enforcement. It matters most in S5 (Groq) and
S8b (CrewAI), when the temptation to import directly is highest.

Parsed with `ast` rather than grepped: a docstring explaining why Groq lives behind an
adapter is not coupling, and a regex that fails on prose trains people to disable the test.
Only real imports and real symbol references count.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
API_APP = REPO_ROOT / "apps" / "api" / "app"
ADAPTERS = API_APP / "adapters"

VENDOR_MODULES = {"groq", "crewai", "autogen", "ag2", "langchain"}


def _non_adapter_sources() -> list[Path]:
    return [p for p in API_APP.rglob("*.py") if ADAPTERS not in p.parents]


def _vendor_imports(tree: ast.AST) -> list[str]:
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0].lower() in VENDOR_MODULES:
                    found.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0].lower()
            if root in VENDOR_MODULES:
                found.append(f"from {node.module} import ...")
    return found


def _vendor_symbols(tree: ast.AST) -> list[str]:
    """Catches `groq.Client(...)` even without a top-level import."""
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id.lower() in VENDOR_MODULES:
            found.append(node.id)
        elif isinstance(node, ast.Attribute):
            value = node.value
            if isinstance(value, ast.Name) and value.id.lower() in VENDOR_MODULES:
                found.append(f"{value.id}.{node.attr}")
    return found


def test_no_vendor_sdk_outside_the_adapter_package():
    offenders: list[str] = []
    for path in _non_adapter_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for hit in _vendor_imports(tree) + _vendor_symbols(tree):
            offenders.append(f"{path.relative_to(REPO_ROOT)}: {hit}")

    assert not offenders, (
        "Vendor SDK used outside apps/api/app/adapters — put it behind a Protocol:\n"
        + "\n".join(offenders)
    )


def test_adapter_protocols_exist_and_are_importable():
    from app.adapters import OutfitAdvisor, TrendSource, WardrobeAnalyzer

    for protocol in (WardrobeAnalyzer, OutfitAdvisor, TrendSource):
        assert callable(protocol)


def test_domain_does_not_import_adapters():
    """Dependency direction: adapters depend on domain, never the reverse."""
    for path in (API_APP / "domain").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("app.adapters"):
                raise AssertionError(f"{path.name} imports app.adapters")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("app.adapters"), (
                        f"{path.name} imports app.adapters"
                    )


def test_domain_models_name_no_provider_concept():
    """The domain speaks garments, not models. No provider or model id in a field name."""
    from app.domain import models

    banned = {"groq", "model_id", "provider", "crewai", "qwen", "gpt"}
    for name in dir(models):
        attribute = getattr(models, name)
        fields = getattr(attribute, "model_fields", None)
        if not fields:
            continue
        for field_name in fields:
            assert not any(token in field_name.lower() for token in banned), (
                f"{name}.{field_name} leaks a provider concept into the domain"
            )
