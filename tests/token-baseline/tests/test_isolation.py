import copy
from pathlib import Path

import pytest

from analyze.isolation import IsolationError, check_isolation
from tests import build


def init_with(**changes):
    init = copy.deepcopy(build.PROBE_INIT)
    for key, edit in changes.items():
        edit(init[key])
    return init


def test_isolation_ok_for_probe_init():
    check_isolation(build.PROBE_INIT, Path(build.REPO))


def test_isolation_flags_foreign_plugin():
    init = init_with(plugins=lambda p: p.append({"name": "datadog", "path": "/x", "source": "datadog@market"}))
    with pytest.raises(IsolationError, match="datadog"):
        check_isolation(init, Path(build.REPO))


def test_isolation_flags_budgetpowers_from_another_path():
    init = init_with(plugins=lambda p: p[0].update(path="/custom-budgetpowers"))
    with pytest.raises(IsolationError, match="custom-budgetpowers"):
        check_isolation(init, Path(build.REPO))


def test_isolation_flags_namespaced_foreign_skill():
    init = init_with(skills=lambda s: s.append("cp-engineer-core:codebase-simplifier"))
    with pytest.raises(IsolationError, match="cp-engineer-core:codebase-simplifier"):
        check_isolation(init, Path(build.REPO))


def test_isolation_flags_mcp_server():
    init = init_with(mcp_servers=lambda m: m.append({"name": "github", "status": "connected"}))
    with pytest.raises(IsolationError, match="github"):
        check_isolation(init, Path(build.REPO))


def test_isolation_flags_agents_md_plugin():
    init = init_with(plugins=lambda p: p.append({"name": "cc-plugin-agents-md", "path": "builtin", "source": "cc-plugin-agents-md@builtin"}))
    with pytest.raises(IsolationError, match="cc-plugin-agents-md"):
        check_isolation(init, Path(build.REPO))


def test_isolation_flags_missing_bootstrap():
    init = init_with(skills=lambda s: s.remove("budgetpowers:using-budgetpowers"))
    with pytest.raises(IsolationError, match="using-budgetpowers"):
        check_isolation(init, Path(build.REPO))
