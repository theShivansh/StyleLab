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

VENDOR_MODULES = {"groq", "crewai", "autogen", "ag2", "langchain", "exa_py", "exa"}


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


# --- model ids ---------------------------------------------------------------------------

#: CLAUDE.md: "Model IDs appear in exactly two places: `docs/DEPLOYMENT.md` and the adapter
#: config." `app/config.py` is that config. Everywhere else reads it.
MODEL_ID_HOME = "config.py"

#: Vendor prefixes rather than a list of ids — a test naming `qwen/qwen3.8-27b` would itself
#: become a third place a model id lives, which is the thing being forbidden.
MODEL_ID_PREFIXES = ("qwen/", "openai/gpt", "llama-3", "llama3-", "gemma", "mixtral")


def _string_literals(tree: ast.AST) -> list[str]:
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]


def test_no_model_id_literal_outside_the_adapter_config():
    """The rule the two greps in CLAUDE.md were reaching for.

    Those greps — `git grep -i groq` outside `adapters/` — never came back empty and never
    could: `Settings` has to name its own fields `groq_api_key` and `groq_text_model`
    because they map to `GROQ_*` environment variables, and prose in a docstring is not
    coupling. Enforcing the literal grep would mean either renaming the settings away from
    their env vars or deleting the explanations, both of which make the code worse.

    What actually matters is narrower and checkable: a model **id** must not be written down
    anywhere except the adapter config. An id baked into a route handler or a prompt survives
    a config change and outlives the deprecation notice.

    String literals only, via `ast` — a docstring that mentions a model id in prose is
    documentation, and the parser tells the difference.
    """
    offenders: list[str] = []
    for path in API_APP.rglob("*.py"):
        if path.name == MODEL_ID_HOME:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for literal in _string_literals(tree):
            # Docstrings are Constant nodes too; skip anything long enough to be prose.
            if len(literal) > 120:
                continue
            for prefix in MODEL_ID_PREFIXES:
                if prefix in literal.lower():
                    offenders.append(f"{path.relative_to(REPO_ROOT)}: {literal!r}")

    assert not offenders, (
        "model id written outside the adapter config — read it from Settings instead:\n"
        + "\n".join(offenders)
    )


def test_the_adapter_config_does_hold_the_model_ids():
    """The other half: if the ids moved out of config, the test above would pass vacuously."""
    from app.config import Settings

    fields = Settings.model_fields
    for name in ("groq_text_model", "groq_vision_model", "groq_vision_fallback_model"):
        assert name in fields, f"{name} is no longer configuration"
        assert fields[name].default, f"{name} has no configured default"


#: The workflow directory. Not Python, so `ast` cannot help — but a YAML file is
#: configuration rather than prose, and a plain text scan is exactly right for it.
WORKFLOWS = REPO_ROOT / ".github" / "workflows"


def test_ci_does_not_pin_a_model_id():
    """The third place model ids were living, which neither rule could see.

    CLAUDE.md allows them in `docs/DEPLOYMENT.md` and the adapter config. `live-smoke` also set
    `GROQ_VISION_MODEL` and friends in its `env:` block, and the test above only scans
    `apps/api/app/` — so the violation was invisible to the guard that exists for it.

    Worse than untidy: those variables **override** the configured defaults. A model change
    in `app/config.py` would have left the availability canary checking the old ids and
    reporting green, which is the precise failure the canary exists to prevent.
    """
    if not WORKFLOWS.is_dir():  # pragma: no cover - CI config may be absent in a fork
        return

    offenders: list[str] = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                # A comment explaining why the ids are absent is not a model id.
                continue
            for prefix in MODEL_ID_PREFIXES:
                if prefix in stripped.lower():
                    offenders.append(f"{path.name}:{number}: {stripped}")

    assert not offenders, (
        "CI pins a model id, which overrides the configured default and makes the "
        "availability check test the wrong thing:\n" + "\n".join(offenders)
    )
