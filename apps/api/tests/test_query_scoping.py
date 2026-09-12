"""Architectural guard — there is no unscoped read path.

prompts/04 requires that "every query filters on `user_id`; there is no unscoped read path,
not even for admin or debug". A test that checked each existing method would pass today and
say nothing about the method somebody adds next month, so this checks the shape of the code
instead:

  * every `select()` in the repository package is built inside a `_scoped*` helper, and
    every such helper takes `user_id` and filters on it;
  * no owned row is loaded by primary key, which would skip the filter entirely;
  * every public method of every repository takes `user_id`;
  * nothing under `app/` imports the test stubs (Case 25 — no product path to a double).

Parsed with `ast`, for the same reason as tests/test_adapter_boundary.py: a comment about
scoping is not a scoping bug, and a guard that fires on prose gets switched off.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
API_APP = REPO_ROOT / "apps" / "api" / "app"
REPOSITORIES = API_APP / "repositories"

#: Rows whose primary-key load would bypass the scoped select.
OWNED_ROWS = {"WardrobeItemRow", "AssetRow", "OutfitRow", "OutfitItemRow", "StyleProfileRow"}
#: Every select must be built in a function whose name starts with this.
SCOPED_PREFIX = "_scoped"


def _repository_sources() -> list[Path]:
    return sorted(REPOSITORIES.rglob("*.py"))


def _functions(tree: ast.AST) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)]


def _enclosing_function(tree: ast.Module, target: ast.AST) -> str | None:
    for function in _functions(tree):
        if any(node is target for node in ast.walk(function)):
            return function.name
    return None


def _calls_named(tree: ast.AST, name: str) -> list[ast.Call]:
    found: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        callee = node.func
        called = callee.id if isinstance(callee, ast.Name) else getattr(callee, "attr", "")
        if called == name:
            found.append(node)
    return found


def test_every_select_is_built_in_a_scoped_helper():
    """The invariant, stated structurally.

    Not "these methods filter correctly" — that would pass today and say nothing about the
    method somebody adds next month. If a query cannot be built outside a scoped helper,
    an unscoped read has nowhere to live.
    """
    offenders: list[str] = []
    builders: set[str] = set()

    for path in _repository_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for call in _calls_named(tree, "select"):
            function = _enclosing_function(tree, call)
            if function and function.startswith(SCOPED_PREFIX):
                builders.add(f"{path.name}:{function}")
                continue
            offenders.append(
                f"{path.relative_to(REPO_ROOT)}:{call.lineno} builds a select() in "
                f"{function}() — route it through a {SCOPED_PREFIX}* helper"
            )

    assert not offenders, "\n".join(offenders)
    assert builders, "no select found at all — has the repository moved?"


def test_every_scoped_helper_takes_and_applies_user_id():
    seen: list[str] = []
    for path in _repository_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for function in _functions(tree):
            if not function.name.startswith(SCOPED_PREFIX):
                continue
            seen.append(function.name)

            arguments = {a.arg for a in function.args.args} | {
                a.arg for a in function.args.kwonlyargs
            }
            assert "user_id" in arguments, f"{path.name}:{function.name} takes no user_id"

            source = ast.unparse(function)
            assert ".where(" in source, f"{path.name}:{function.name} filters nothing"
            filters = source.split(".where(", 1)[1]
            assert "user_id" in filters, (
                f"{path.name}:{function.name} has a where() that never mentions user_id"
            )
    assert seen, f"no {SCOPED_PREFIX}* helper found"


def test_no_primary_key_load_of_an_owned_row():
    """`Session.get(WardrobeItemRow, item_id)` is the obvious way around a scoped select:
    it loads by primary key and ignores the filter entirely. Forbidden explicitly, because
    it is the one bypass that looks like ordinary SQLAlchemy."""
    offenders: list[str] = []
    for path in sorted(API_APP.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for call in _calls_named(tree, "get"):
            for argument in call.args:
                name = (
                    argument.id
                    if isinstance(argument, ast.Name)
                    else getattr(argument, "attr", "")
                )
                if name in OWNED_ROWS:
                    offenders.append(
                        f"{path.relative_to(REPO_ROOT)}:{call.lineno} loads {name} by "
                        f"primary key, bypassing the user_id filter"
                    )
    assert not offenders, "\n".join(offenders)


def test_every_public_repository_method_takes_user_id():
    """Including anything an admin or debug screen might reach for."""
    offenders: list[str] = []

    for path in _repository_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef) or not node.name.endswith("Repository"):
                continue
            for method in node.body:
                if not isinstance(method, ast.FunctionDef | ast.AsyncFunctionDef):
                    continue
                if method.name.startswith("_"):
                    continue
                arguments = {a.arg for a in method.args.args} | {
                    a.arg for a in method.args.kwonlyargs
                }
                # `add_item` takes a WardrobeItem, which carries its own user_id by type.
                if "user_id" in arguments or "item" in arguments:
                    continue
                offenders.append(f"{node.name}.{method.name} takes no user_id")

    assert not offenders, "\n".join(offenders)


def test_no_product_code_imports_the_test_stubs():
    """AI-EVAL-CASES Case 25: the running application has no path to a test double."""
    offenders: list[str] = []
    for path in API_APP.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.ImportFrom):
                modules.append(node.module or "")
            elif isinstance(node, ast.Import):
                modules.extend(a.name for a in node.names)
            for module in modules:
                if module.startswith("tests") or "stubs" in module:
                    offenders.append(f"{path.relative_to(REPO_ROOT)} imports {module}")

    assert not offenders, "\n".join(offenders)
