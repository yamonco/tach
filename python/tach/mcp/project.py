from __future__ import annotations

from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypedDict

import tomli_w

from tach.filesystem import build_project_config_path, find_project_config_root
from tach.mcp.payloads import DEFAULT_LIMIT, digest, truncate_items
from tach.modularity import build_modules
from tach.parsing import combine_exclude_paths, parse_project_config

if TYPE_CHECKING:
    from tach.extension import ProjectConfig


class DependencyRule(TypedDict):
    path: str
    dependency: str


def resolve_project_root(project_root_value: str | None = None) -> Path:
    if project_root_value:
        return Path(project_root_value).expanduser().resolve()
    return find_project_config_root() or Path.cwd().resolve()


def project_ref(project_root_value: str | Path) -> str:
    return urlsafe_b64encode(
        str(Path(project_root_value).expanduser().resolve()).encode()
    ).decode()


def project_root_from_ref(project_ref_value: str) -> Path:
    return Path(urlsafe_b64decode(project_ref_value.encode()).decode()).resolve()


def resolve_project_path(root: Path, path: str | Path) -> Path:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    return candidate.resolve()


def rel_project_path(root: Path, path: str | Path) -> Path:
    return resolve_project_path(root, path).relative_to(root)


def resource_uris(root: Path) -> dict[str, str]:
    ref = project_ref(root)
    return {
        "config": f"tach://project-config/{ref}",
        "summary": f"tach://project-summary/{ref}",
        "graph": f"tach://project-graph/{ref}",
        "dependency_map": f"tach://dependency-map/{ref}?view=summary",
        "modularity_report": f"tach://modularity-report/{ref}?view=summary",
        "delta": f"tach://delta/{ref}/main",
    }


def missing_config_result(mode: str, root: Path) -> dict[str, Any]:
    return {
        "ok": False,
        "mode": mode,
        "project_root": str(root),
        "error": f"No Tach config found below '{root}'.",
        "next_action": "Call tach_onboard, then tach_configure action='create_config'.",
    }


def default_python_file(root: Path, config: ProjectConfig) -> str | None:
    for source_root in config.source_roots:
        absolute_root = resolve_project_path(root, source_root)
        if not absolute_root.exists():
            continue
        for candidate in sorted(absolute_root.rglob("*.py")):
            if "__pycache__" not in candidate.parts:
                return str(candidate.relative_to(root))
    return None


def project_config(
    root: Path,
    exclude: list[str] | None = None,
) -> ProjectConfig:
    config = parse_project_config(root)
    if config is None:
        raise ValueError(f"No Tach config found below '{root}'.")
    config.exclude = combine_exclude_paths(exclude, config.exclude)
    return config


def config_summary(config: ProjectConfig) -> dict[str, Any]:
    modules = build_modules(config)
    return {
        "source_roots": [str(root) for root in config.source_roots],
        "modules": [asdict(module) for module in modules],
        "interfaces": [
            {
                "expose": interface.expose,
                "from_modules": interface.from_modules,
                "visibility": interface.visibility,
                "data_types": interface.data_types,
            }
            for interface in config.all_interfaces()
        ],
        "utility_paths": config.utility_paths(),
        "module_paths": config.module_paths(),
        "exclude": config.exclude,
        "exact": config.exact,
        "root_module": config.root_module,
        "forbid_circular_dependencies": config.forbid_circular_dependencies,
    }


def compact_config_summary(
    root: Path,
    config: ProjectConfig,
    *,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> dict[str, Any]:
    full = config_summary(config)
    module_paths = list(full["module_paths"])
    ref = project_ref(root)
    return {
        "project_root": str(root),
        "source_roots": full["source_roots"],
        "module_count": len(module_paths),
        "interface_count": len(full["interfaces"]),
        "utility_count": len(full["utility_paths"]),
        "dependency_count": sum(
            len(module.get("depends_on", [])) for module in full["modules"]
        ),
        "exact": full["exact"],
        "root_module": full["root_module"],
        "forbid_circular_dependencies": full["forbid_circular_dependencies"],
        "digest": digest(full),
        "resource_uri": f"tach://project-config/{ref}",
        "summary_resource_uri": f"tach://project-summary/{ref}",
        "modules": truncate_items(module_paths, limit=limit, offset=offset),
        "truncated": offset + max(0, limit) < len(module_paths),
    }


def save_config(
    root: Path,
    source_roots: list[str],
    modules: list[str],
    utilities: list[str] | None = None,
    dependencies: list[DependencyRule] | None = None,
    *,
    forbid_circular_dependencies: bool = False,
) -> ProjectConfig:
    config_path = build_project_config_path(root)
    module_data: list[dict[str, Any]] = [
        {"path": module, "depends_on": []} for module in modules
    ]
    for module in modules:
        if utilities and module in utilities:
            next(item for item in module_data if item["path"] == module)["utility"] = (
                True
            )
    for utility in sorted(set(utilities or []) - set(modules)):
        module_data.append({"path": utility, "depends_on": [], "utility": True})
    for dependency in dependencies or []:
        module = next(
            item for item in module_data if item["path"] == dependency["path"]
        )
        module["depends_on"].append({"path": dependency["dependency"]})
    config_data: dict[str, Any] = {"source_roots": source_roots}
    if forbid_circular_dependencies:
        config_data["forbid_circular_dependencies"] = True
    config_data["modules"] = module_data
    config_path.write_text(tomli_w.dumps(config_data))
    config = parse_project_config(root)
    if config is None:
        raise ValueError(f"Failed to parse new config at '{config_path}'.")
    return config
