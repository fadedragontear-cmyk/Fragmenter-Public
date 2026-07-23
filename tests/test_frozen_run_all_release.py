from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import run_all_executor_v1 as base
import run_all_executor_v9


def test_frozen_run_all_does_not_relaunch_fragmenter(monkeypatch) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    expected = {
        "iso_index": "build_iso_index_frozen_v9",
        "ccsf_extract": "extract_ccsf_frozen_v9",
    }
    for key, internal in expected.items():
        source = base.RunAction(
            key,
            key,
            "subprocess",
            argv=("Fragmenter.exe", f"{key}.py"),
            inputs=("input",),
            outputs=("output",),
        )
        converted = run_all_executor_v9._with_frozen_safe_execution(source)
        assert converted.kind == "internal"
        assert converted.internal == internal
        assert converted.argv == ()
        assert converted.inputs == source.inputs
        assert converted.outputs == source.outputs


def test_source_run_all_keeps_python_subprocess(monkeypatch) -> None:
    monkeypatch.delattr(sys, "frozen", raising=False)
    source = base.RunAction(
        "iso_index",
        "Index ISO Filesystem",
        "subprocess",
        argv=(sys.executable, "iso_index.py"),
    )
    assert run_all_executor_v9._with_frozen_safe_execution(source) is source
