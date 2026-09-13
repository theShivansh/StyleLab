"""CrewAI's LLM interface, implemented over our own `ChatTransport`.

This is the single most load-bearing file in the crew, and it is twenty lines of real work
wrapped in the reason for them.

CrewAI talks to models through LiteLLM by default. Adopting that would mean the crew makes
its own HTTP calls, with its own retry policy, its own timeouts and its own idea of what a
provider error is — and, fatally for this repository, **the crew could not be tested without
an API key**. `tests/ai/` exists because every grounding claim in the product is checkable
for free on every push; a crew that bypassed `ChatTransport` would be the one component
whose behaviour nobody could assert cheaply, which is exactly the component most likely to
produce confident nonsense.

`crewai.BaseLLM` is the documented seam for this. Subclass it, implement `call()`, and every
agent in the crew goes through the same transport as the single-call advisor — the same
retry policy, the same error taxonomy, the same telemetry, and the same `MockGroqProvider`.

## The sync/async bridge

`BaseLLM.call()` is synchronous and CrewAI drives it from its own threads. Our transport is
async. The bridge is `asyncio.run_coroutine_threadsafe` against a loop captured before the
crew starts: the crew itself runs inside `asyncio.to_thread`, so the loop is alive and
running throughout, and each `call()` hands its coroutine back to it and blocks the crew's
thread — never the event loop.

The alternative, `asyncio.run()` inside `call()`, would build and tear down an event loop per
agent call and would break any client holding a connection pool. It looks simpler and is a
bug.

## Structured output

CrewAI passes `response_model` when a task declares `output_pydantic`. That maps onto our
`SchemaSpec`, so the crew gets Groq's strict Structured Outputs rather than a prose response
somebody parses with a regular expression. `docs/AGENT-SYSTEM.md` requires it: no free-text
handoffs between agents.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any, ClassVar

from crewai import BaseLLM
from pydantic import BaseModel

from app.adapters.transport import ChatMessage, ChatResult, ChatTransport, SchemaSpec
from app.domain.schemas import close_and_require

logger = logging.getLogger("stylelab.crew")

#: Groq's context window for the text model, reported to CrewAI so it can bound its own
#: prompt assembly. Not a model id and not a model choice — a number about the wire.
CONTEXT_WINDOW_TOKENS = 128_000


class TransportLLM(BaseLLM):
    """A `crewai.BaseLLM` that speaks `ChatTransport`.

    Holds no vendor client. Every call it makes is one the mock provider can script, which is
    what keeps the whole crew runnable with no key.
    """

    # CrewAI's BaseLLM is a pydantic model in 1.x, so a transport — an arbitrary object —
    # needs saying so before it can be held.
    model_config: ClassVar[dict[str, Any]] = {"arbitrary_types_allowed": True}

    def __init__(
        self,
        transport: ChatTransport,
        *,
        model: str,
        max_tokens: int | None = None,
        timeout_s: float | None = None,
        on_call: Callable[[ChatResult], None] | None = None,
        temperature: float | None = None,
    ) -> None:
        super().__init__(model=model, temperature=temperature)
        # Set through object.__setattr__ so this works whether BaseLLM is a pydantic model
        # or a plain class — CrewAI has changed that between minor versions, and a crew that
        # breaks on a patch release is not worth the elegance.
        object.__setattr__(self, "_transport", transport)
        object.__setattr__(self, "_max_tokens", max_tokens)
        object.__setattr__(self, "_timeout_s", timeout_s)
        object.__setattr__(self, "_on_call", on_call)
        object.__setattr__(self, "_loop", None)

    # --- lifecycle ------------------------------------------------------------------------

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Capture the event loop the transport must run on.

        Called from the async side before the crew is handed to a worker thread. Without it
        `call()` has no loop to hand its coroutine to and says so loudly rather than quietly
        starting a second one.
        """
        object.__setattr__(self, "_loop", loop)

    # --- the CrewAI interface ---------------------------------------------------------------

    def call(
        self,
        messages: str | list[dict[str, str]],
        tools: list[Any] | None = None,
        callbacks: list[Any] | None = None,
        available_functions: dict[str, Any] | None = None,
        from_task: Any | None = None,
        from_agent: Any | None = None,
        response_model: type[BaseModel] | None = None,
    ) -> str:
        loop: asyncio.AbstractEventLoop | None = getattr(self, "_loop", None)
        if loop is None:
            raise RuntimeError(
                "TransportLLM.bind_loop() was never called; the crew has no event loop to "
                "run the transport on"
            )

        coroutine = self._complete(messages, response_model)
        # Blocks this worker thread, not the loop. The crew is already off the loop.
        return asyncio.run_coroutine_threadsafe(coroutine, loop).result()

    def supports_function_calling(self) -> bool:
        """No tools. Every agent in this crew is given its inputs and asked for a judgement.

        A tool would be a second, unaudited route to data — and the one rule the product
        rests on is that the candidate set is fixed in SQL before any model runs. An agent
        that could call a wardrobe tool could widen its own scope.
        """
        return False

    def supports_stop_words(self) -> bool:
        return False

    def get_context_window_size(self) -> int:
        return CONTEXT_WINDOW_TOKENS

    # --- internals ----------------------------------------------------------------------------

    async def _complete(
        self, messages: str | list[dict[str, str]], response_model: type[BaseModel] | None
    ) -> str:
        transport: ChatTransport = self._transport  # type: ignore[attr-defined]
        result = await transport.complete(
            model=self.model,
            messages=_as_chat_messages(messages),
            schema=_schema_for(response_model),
            timeout_s=self._timeout_s,  # type: ignore[attr-defined]
            max_tokens=self._max_tokens,  # type: ignore[attr-defined]
        )
        on_call = self._on_call  # type: ignore[attr-defined]
        if on_call is not None:
            on_call(result)
        return result.content


def _as_chat_messages(messages: str | list[dict[str, str]]) -> list[ChatMessage]:
    """CrewAI's message shape to ours.

    CrewAI sends either a bare string or OpenAI-style `{role, content}` dicts. Content that
    is not a string is serialised rather than dropped — losing part of a prompt silently is
    how an agent comes to answer a question it was never fully asked.
    """
    if isinstance(messages, str):
        return [ChatMessage.text("user", messages)]

    converted: list[ChatMessage] = []
    for message in messages:
        role = str(message.get("role", "user"))
        content = message.get("content", "")
        body = content if isinstance(content, str) else json.dumps(content, default=str)
        converted.append(ChatMessage.text(role, body))
    return converted


def _schema_for(response_model: type[BaseModel] | None) -> SchemaSpec | None:
    """A CrewAI `output_pydantic` model to a strict structured-output request.

    Reuses `close_and_require` so an agent's schema is prepared exactly the way the advice
    and extraction schemas are: every object closed, every property required, optionality
    carried by the type. Two ways of building a strict schema in one codebase is one way too
    many, and the second one is always the one that is wrong on a Friday.
    """
    if response_model is None:
        return None
    return SchemaSpec(
        name=_schema_name(response_model),
        schema=_without_docstrings(close_and_require(response_model)),
        description=(response_model.__doc__ or "").strip().split("\n")[0] or None,
    )


def _without_docstrings(schema: dict[str, Any]) -> dict[str, Any]:
    """Strip object-level `description` from a generated schema.

    Pydantic copies a model's **entire docstring** into its schema description, and the
    docstrings in `crew_contracts.py` are long, because they exist to explain to a reader why
    each agent is there. Measured on a live crew run: 11,123 prompt tokens for one
    composition, a good part of it this project explaining itself to Groq.

    Two reasons that is worth a function rather than a shrug. It is money and latency spent on
    text the model does not need — each agent already has its instructions in the task
    description. And it puts internal design commentary into a third party's request logs,
    which is not a leak of user data but is not something to do by accident either.

    Field-level descriptions would survive this: those come from `Field(description=...)` and
    are written *for* the model. Only the docstring-derived ones on objects go.
    """

    def strip(node: Any) -> Any:
        if isinstance(node, dict):
            return {
                key: strip(value)
                for key, value in node.items()
                if not (key == "description" and _is_object(node))
            }
        if isinstance(node, list):
            return [strip(item) for item in node]
        return node

    return strip(schema)


def _is_object(node: dict[str, Any]) -> bool:
    """An object node — where Pydantic puts the class docstring."""
    return "properties" in node or node.get("type") == "object"


def _schema_name(model: type[BaseModel]) -> str:
    """`AgentCritique` -> `agent_critique`. Providers want a snake_case name."""
    name = model.__name__
    return "".join(f"_{c.lower()}" if c.isupper() else c for c in name).lstrip("_")


__all__ = ["CONTEXT_WINDOW_TOKENS", "TransportLLM"]
