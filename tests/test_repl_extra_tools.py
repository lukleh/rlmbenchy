from __future__ import annotations

from rlmbenchy.rlm.repl import LocalProcessReplRuntime


def test_extra_tools_callable_from_repl():
    runtime = LocalProcessReplRuntime(
        tools={"my_tool": lambda x: str(int(x) * 2)},
    )
    runtime.start()
    try:
        result = runtime.execute("result = my_tool(21)\nprint(result)")
        assert isinstance(result, str)
        assert "42" in result
    finally:
        runtime.shutdown()
