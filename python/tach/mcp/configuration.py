from __future__ import annotations

from typing import Any, Literal

from tach import extension
from tach.filesystem import build_project_config_path
from tach.filesystem import install_pre_commit as install_pre_commit_hook
from tach.mcp.payloads import digest
from tach.mcp.project import (
    DependencyRule,
    config_summary,
    project_config,
    resolve_project_root,
    save_config,
)
from tach.mcp.server import mcp
from tach.parsing import dump_project_config_to_toml


@mcp.tool()
def tach_configure(
    action: Literal[
        "create_config",
        "edit_module",
        "edit_dependency",
        "sync_dependencies",
        "install_pre_commit",
    ],
    project_root: str,
    source_roots: list[str] | None = None,
    modules: list[str] | None = None,
    utilities: list[str] | None = None,
    dependencies: list[DependencyRule] | None = None,
    path: str | None = None,
    dependency: str | None = None,
    module_action: Literal["create", "delete", "mark_utility", "unmark_utility"]
    | None = None,
    dependency_action: Literal["add", "remove"] | None = None,
    force: bool = False,
    add_only: bool = False,
    include_config: bool = False,
) -> dict[str, Any]:
    """Create or edit Tach config, sync dependencies, or install pre-commit."""
    root = resolve_project_root(project_root)
    result: dict[str, Any]

    if action == "create_config":
        if source_roots is None or modules is None:
            raise ValueError("source_roots and modules are required for create_config.")
        config_path = build_project_config_path(root)
        if config_path.exists() and not force:
            raise ValueError(
                f"Config already exists at '{config_path}'. Pass force=true."
            )
        config = save_config(root, source_roots, modules, utilities, dependencies)
        result = {
            "ok": True,
            "action": action,
            "project_root": str(root),
            "config_path": str(config_path),
            "module_count": len(config.module_paths()),
            "dependency_count": len(dependencies or []),
        }
    elif action == "edit_module":
        if path is None or module_action is None:
            raise ValueError("path and module_action are required for edit_module.")
        config = project_config(root)
        if module_action == "create":
            config.create_module(path)
        elif module_action == "delete":
            config.delete_module(path)
        elif module_action == "mark_utility":
            config.mark_module_as_utility(path)
        else:
            config.unmark_module_as_utility(path)
        config.save_edits()
        result = {"ok": True, "action": action, "project_root": str(root), "path": path}
    elif action == "edit_dependency":
        if path is None or dependency is None or dependency_action is None:
            raise ValueError(
                "path, dependency, and dependency_action are required for edit_dependency."
            )
        config = project_config(root)
        if dependency_action == "add":
            config.add_dependency(path, dependency)
        else:
            config.remove_dependency(path, dependency)
        config.save_edits()
        result = {
            "ok": True,
            "action": action,
            "project_root": str(root),
            "path": path,
            "dependency": dependency,
        }
    elif action == "sync_dependencies":
        config = project_config(root)
        before = dump_project_config_to_toml(config)
        extension.sync_project(project_root=root, project_config=config, add=add_only)
        after_config = project_config(root)
        result = {
            "ok": True,
            "action": action,
            "changed": before != dump_project_config_to_toml(after_config),
            "project_root": str(root),
            "digest": digest(config_summary(after_config)),
        }
    else:
        installed, warning = install_pre_commit_hook(root)
        result = {
            "ok": installed,
            "action": action,
            "project_root": str(root),
            "installed": installed,
            "warning": warning,
        }

    if include_config and action != "install_pre_commit":
        result["config"] = config_summary(project_config(root))
    return result
