from __future__ import annotations

import json
from pathlib import Path

from tach import mcp as tach_mcp

EXAMPLE_ROOT = Path(__file__).parent / "example" / "valid"


def test_tach_mcp_onboard_summary():
    result = tach_mcp.tach_onboard(str(EXAMPLE_ROOT))

    assert result["mcp_protocol"] == tach_mcp.MCP_PROTOCOL_VERSION
    assert result["configured"] is True
    assert result["project"]["module_count"] == 4
    assert result["resources"]["config"].startswith("tach://project-config/")


def test_tach_mcp_onboard_unconfigured(tmp_path):
    result = tach_mcp.tach_onboard(str(tmp_path), intent="bootstrap")

    assert result["configured"] is False
    assert "tach_configure" in result["next_actions"][0]


def test_tach_mcp_configure_project(tmp_path):
    project_root = tmp_path / "project"
    src = project_root / "src"
    src.mkdir(parents=True)
    (src / "module_one.py").write_text("import module_two\n")
    (src / "module_two.py").write_text("")
    (src / "module_three.py").write_text("")

    created = tach_mcp.tach_configure(
        "create_config",
        str(project_root),
        source_roots=["src"],
        modules=["module_one", "module_two"],
        utilities=["module_two"],
        dependencies=[{"path": "module_one", "dependency": "module_two"}],
    )
    assert created["ok"] is True
    assert (project_root / "tach.toml").exists()

    edited = tach_mcp.tach_configure(
        "edit_dependency",
        str(project_root),
        path="module_one",
        dependency="module_two",
        dependency_action="remove",
    )
    assert edited["ok"] is True

    module_edited = tach_mcp.tach_configure(
        "edit_module",
        str(project_root),
        path="module_three",
        module_action="create",
        include_config=True,
    )
    assert "module_three" in module_edited["config"]["module_paths"]


def test_tach_mcp_lint_defaults_to_strong_checks():
    result = tach_mcp.tach_lint(str(EXAMPLE_ROOT))

    assert result["ok"] is True
    assert result["checks"] == ["boundaries", "external", "unused"]
    assert result["warning_count"] == 1
    assert result["boundaries"]["diagnostics"]["items"][0]["severity"] == "warning"


def test_tach_mcp_analyze_imports_and_report():
    imports = tach_mcp.tach_imports(
        path="domain_one/__init__.py",
        project_root=str(EXAMPLE_ROOT),
    )
    assert imports["imports"][0]["module_path"] == "domain_two.x"

    report = tach_mcp.tach_report(path="domain_two", project_root=str(EXAMPLE_ROOT))
    assert report["mode"] == "report"
    assert "report" in report


def test_tach_mcp_analyze_graph_and_dependency_map():
    graph = tach_mcp.tach_graph(str(EXAMPLE_ROOT))

    assert graph["graph_preview"].startswith("graph TD")
    assert "resource_uri" in graph

    dep_map = tach_mcp.tach_map(str(EXAMPLE_ROOT), limit=1)
    assert dep_map["file_count"] > 1
    assert dep_map["entries"]["truncated"] is True
    assert "map" not in dep_map


def test_tach_mcp_analyze_closure_delta_and_changed_files():
    closure = tach_mcp.tach_map(
        str(EXAMPLE_ROOT),
        mode="closure",
        path="domain_two/some_file.py",
    )
    assert "domain_two/some_file.py" in closure["closure"]

    delta = tach_mcp.tach_map(
        str(EXAMPLE_ROOT),
        mode="delta",
        changed=["domain_two/other.py"],
    )
    assert delta["changed_files"] == ["domain_two/other.py"]
    assert "domain_two/some_file.py" in delta["affected"]["items"]


def test_tach_mcp_analyze_modularity_export(tmp_path):
    summary = tach_mcp.tach_modularity(str(Path.cwd()), force=True)
    assert summary["module_count"] > 1
    assert "full_configuration" not in summary

    output_path = tmp_path / "report.json"
    exported = tach_mcp.tach_modularity(
        str(Path.cwd()),
        mode="export",
        output_path=str(output_path),
        force=True,
    )
    assert exported["ok"] is True
    assert json.loads(output_path.read_text())["repo"] == "tach"


def test_tach_mcp_test_affected():
    result = tach_mcp.tach_test(
        str(Path.cwd()),
        pytest_args=["python/tests/test_cli.py", "-q"],
        max_bytes=1000,
    )

    assert result["ok"] is True
    assert result["stdout_bytes"] > 0


def test_tach_mcp_prompts():
    prompt = tach_mcp.diagnose_tach_boundaries(str(EXAMPLE_ROOT))

    assert "tach_lint" in prompt
