from __future__ import annotations

from pathlib import Path

from radon.complexity import cc_visit
from radon.visitors import Class


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MAX_BLOCK_COMPLEXITY = 17
HOTSPOT_BUDGETS = {
    ("app/config.py", "Settings.from_env"): 10,
    ("app/ingestion/chunker.py", "DocumentChunker._split_with_spans"): 8,
    ("app/llm_client.py", "ModelGateway._compact_evidence"): 8,
    ("app/vectorstore/chroma.py", "ChromaVectorStore.upsert"): 10,
    ("app/vectorstore/memory.py", "InMemoryVectorStore.upsert"): 10,
    ("app/vectorstore/upsert.py", "build_upsert_plan"): 6,
}


def _complexity_by_name(relative_path: str) -> dict[str, int]:
    source = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
    result: dict[str, int] = {}
    for block in cc_visit(source):
        if isinstance(block, Class):
            result.update(
                {f"{block.name}.{method.name}": method.complexity for method in block.methods}
            )
        else:
            result[block.name] = block.complexity
    return result


def test_refactored_hotspots_stay_within_their_complexity_budgets() -> None:
    measured = {
        (relative_path, symbol): _complexity_by_name(relative_path).get(symbol)
        for relative_path, symbol in HOTSPOT_BUDGETS
    }

    assert all(value is not None for value in measured.values()), measured
    assert not {
        key: {"actual": value, "budget": HOTSPOT_BUDGETS[key]}
        for key, value in measured.items()
        if value is not None and value > HOTSPOT_BUDGETS[key]
    }


def test_application_has_no_very_high_complexity_blocks() -> None:
    violations: dict[str, int] = {}
    for path in sorted((PROJECT_ROOT / "app").rglob("*.py")):
        relative_path = path.relative_to(PROJECT_ROOT).as_posix()
        for symbol, complexity in _complexity_by_name(relative_path).items():
            if complexity > MAX_BLOCK_COMPLEXITY:
                violations[f"{relative_path}:{symbol}"] = complexity

    assert not violations
