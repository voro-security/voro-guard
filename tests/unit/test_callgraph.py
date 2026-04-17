import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from voro_mcp.core.callgraph import parse_solidity_functions
from voro_mcp.core.parser import extract_symbols
from voro_mcp.models.schemas import CallgraphRequest
from voro_mcp.routes.query import get_callgraph


def _sample_contract() -> str:
    return (
        "pragma solidity ^0.8.0;\n"
        "contract Demo {\n"
        "  function delegate() public { updateBalance(); }\n"
        "  function updateBalance() internal { transfer(); }\n"
        "  function transfer() private { }\n"
        "  function ping() external payable { updateBalance(); }\n"
        "  fallback() external payable { updateBalance(); }\n"
        "}\n"
    )


def test_solidity_visibility_reachability_mapping() -> None:
    source = _sample_contract()
    functions = parse_solidity_functions(source)

    assert functions["delegate"].visibility == "public"
    assert functions["delegate"].reachable is True
    assert functions["updateBalance"].visibility == "internal"
    assert functions["updateBalance"].reachable is True  # transitively reachable via delegate/ping
    assert functions["transfer"].visibility == "private"
    assert functions["transfer"].reachable is True  # transitively reachable via updateBalance
    assert functions["ping"].visibility == "external"
    assert functions["ping"].reachable is True
    assert functions["fallback"].reachable is True


def test_extract_symbols_includes_solidity_reachability_fields() -> None:
    symbols = extract_symbols("Demo.sol", _sample_contract())
    functions = {s["name"]: s for s in symbols if s.get("kind") == "function"}

    assert functions["delegate"]["reachable"] is True
    assert functions["updateBalance"]["reachable"] is True
    assert functions["ping"]["reachable"] is True
    assert functions["fallback"]["reachable"] is True


def test_callgraph_endpoint_returns_nested_structure(tmp_path: Path) -> None:
    sol = tmp_path / "Demo.sol"
    sol.write_text(_sample_contract(), encoding="utf-8")

    res = get_callgraph(
        CallgraphRequest(file=str(sol.resolve()), entry_function="delegate", max_depth=10)
    )
    assert "entry_points" in res
    assert len(res["entry_points"]) == 1
    root = res["entry_points"][0]
    assert root["name"] == "delegate"
    assert root["visibility"] == "public"
    assert root["calls"][0]["name"] == "updateBalance"


def test_callgraph_depth_limit_respected(tmp_path: Path) -> None:
    sol = tmp_path / "Demo.sol"
    sol.write_text(_sample_contract(), encoding="utf-8")

    res = get_callgraph(
        CallgraphRequest(file=str(sol.resolve()), entry_function="delegate", max_depth=1)
    )
    root = res["entry_points"][0]
    assert len(root["calls"]) == 1
    assert root["calls"][0]["name"] == "updateBalance"
    assert root["calls"][0]["calls"] == []


def test_callgraph_unknown_entry_function_returns_graceful_error(tmp_path: Path) -> None:
    sol = tmp_path / "Demo.sol"
    sol.write_text(_sample_contract(), encoding="utf-8")

    res = get_callgraph(
        CallgraphRequest(file=str(sol.resolve()), entry_function="doesNotExist", max_depth=10)
    )
    assert res["entry_points"] == []
    assert "error" in res


def test_no_explicit_visibility_defaults_to_public() -> None:
    source = (
        "pragma solidity ^0.4.24;\n"
        "contract Legacy {\n"
        "  function noVisibility() { }\n"
        "}\n"
    )
    functions = parse_solidity_functions(source)
    assert functions["noVisibility"].visibility == "public"
    assert functions["noVisibility"].reachable is True


def test_transitive_reachability_through_internal_chain() -> None:
    source = (
        "contract Chain {\n"
        "  function entry() public { mid(); }\n"
        "  function mid() internal { deep(); }\n"
        "  function deep() private { }\n"
        "  function isolated() internal { }\n"
        "}\n"
    )
    functions = parse_solidity_functions(source)
    assert functions["entry"].reachable is True
    assert functions["mid"].reachable is True  # called by entry (public)
    assert functions["deep"].reachable is True  # called by mid, transitively reachable
    assert functions["isolated"].reachable is False  # no public caller


def test_circular_calls_do_not_infinite_loop() -> None:
    source = (
        "contract Circular {\n"
        "  function a() public { b(); }\n"
        "  function b() internal { c(); }\n"
        "  function c() internal { b(); }\n"
        "}\n"
    )
    functions = parse_solidity_functions(source)
    assert functions["a"].reachable is True
    assert functions["b"].reachable is True
    assert functions["c"].reachable is True
