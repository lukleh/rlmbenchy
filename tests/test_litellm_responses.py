from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel

from rlmbenchy.litellm_responses import drain_litellm_responses_stream


@dataclass
class _EnumLike:
    value: str


@dataclass
class _Event:
    type: _EnumLike
    output_index: int | None = None
    item: object | None = None


@dataclass
class _Item:
    type: str
    content: list[object]


@dataclass
class _Response:
    output: list[object]


class _PydanticResponse(BaseModel):
    output: list[object]
    usage: dict[str, object] = {}
    model: str = "test-model"


@dataclass
class _Completed:
    response: _Response


class _Stream:
    def __init__(self, events: list[object], response: _Response) -> None:
        self._events = list(events)
        self.completed_response = _Completed(response=response)

    def __iter__(self):
        return iter(self._events)


def test_drain_litellm_responses_stream_hydrates_output_from_done_events() -> None:
    message = _Item(type="message", content=[{"type": "output_text", "text": "hello"}])
    stream = _Stream(
        events=[
            _Event(
                type=_EnumLike("response.output_item.added"),
                output_index=0,
                item=_Item(type="message", content=[]),
            ),
            _Event(
                type=_EnumLike("response.output_item.done"),
                output_index=0,
                item=message,
            ),
        ],
        response=_Response(output=[]),
    )

    response = drain_litellm_responses_stream(stream)

    assert response["output"] == [
        {
            "type": "message",
            "content": [{"type": "output_text", "text": "hello"}],
        }
    ]


def test_drain_litellm_responses_stream_keeps_existing_output() -> None:
    existing = _Item(type="message", content=[{"type": "output_text", "text": "kept"}])
    stream = _Stream(
        events=[],
        response=_Response(output=[existing]),
    )

    response = drain_litellm_responses_stream(stream)

    assert response["output"] == [
        {
            "type": "message",
            "content": [{"type": "output_text", "text": "kept"}],
        }
    ]


def test_drain_litellm_responses_stream_merges_done_and_fallback_items() -> None:
    finalized = _Item(
        type="message", content=[{"type": "output_text", "text": "hello"}]
    )
    fallback_only = _Item(
        type="message", content=[{"type": "output_text", "text": "partial"}]
    )
    stream = _Stream(
        events=[
            _Event(
                type=_EnumLike("response.output_item.done"),
                output_index=0,
                item=finalized,
            ),
            _Event(
                type=_EnumLike("response.output_item.added"),
                output_index=1,
                item=fallback_only,
            ),
        ],
        response=_Response(output=[]),
    )

    response = drain_litellm_responses_stream(stream)

    assert response["output"] == [
        {
            "type": "message",
            "content": [{"type": "output_text", "text": "hello"}],
        },
        {
            "type": "message",
            "content": [{"type": "output_text", "text": "partial"}],
        },
    ]


def test_drain_litellm_responses_stream_hydrates_dict_completed_response() -> None:
    stream = _Stream(
        events=[
            _Event(
                type=_EnumLike("response.output_item.done"),
                output_index=0,
                item={
                    "type": "message",
                    "content": [{"type": "output_text", "text": "hello"}],
                },
            ),
        ],
        response={"output": [], "usage": {"input_tokens": 3}, "model": "test-model"},
    )

    response = drain_litellm_responses_stream(stream)

    assert response == {
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": "hello"}],
            }
        ],
        "usage": {"input_tokens": 3},
        "model": "test-model",
    }


def test_drain_litellm_responses_stream_normalizes_pydantic_completed_response() -> (
    None
):
    message = _Item(type="message", content=[{"type": "output_text", "text": "hello"}])
    stream = _Stream(
        events=[
            _Event(
                type=_EnumLike("response.output_item.done"),
                output_index=0,
                item=message,
            ),
        ],
        response=_PydanticResponse(output=[]),
    )

    response = drain_litellm_responses_stream(stream)

    assert response["output"][0]["content"][0]["text"] == "hello"
    assert response["model"] == "test-model"
