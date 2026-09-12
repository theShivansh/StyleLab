"""`GroqChatTransport` — error mapping, bounded retry, and the transport contract.

The one module in the repository that imports the Groq SDK, so the one place SDK exceptions
can be raised at all. Tested against a fake async client rather than the network: the
subject here is *our* retry loop and *our* error taxonomy, and a live call would test
neither reliably.

Sleeping is patched out. A backoff test that actually waits is a slow test that people stop
running, and the thing worth asserting is the *shape* of the delays, not the elapsed time.
"""

from __future__ import annotations

from typing import Any

import groq
import httpx
import pytest

from app.adapters import groq_transport
from app.adapters.groq_transport import (
    BACKOFF_BASE_S,
    MAX_BACKOFF_S,
    GroqChatTransport,
)
from app.adapters.provider_errors import (
    ProviderContractError,
    ProviderModelMissingError,
    ProviderRateLimitedError,
    ProviderRefusedError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.adapters.transport import ChatMessage, SchemaSpec

MODEL = "test/model"
REQUEST = httpx.Request("POST", "https://api.groq.test/openai/v1/chat/completions")


def status_error(kind: type[Exception], code: int, **headers: str) -> Exception:
    response = httpx.Response(code, headers=headers, request=REQUEST)
    return kind("provider said no", response=response, body=None)


class FakeCompletion:
    """Minimal stand-in for a Groq chat completion object."""

    def __init__(self, content: str | None, *, model: str = MODEL, with_choice: bool = True):
        message = type("M", (), {"content": content})()
        choice = type("C", (), {"message": message})()
        self.choices = [choice] if with_choice else []
        self.model = model
        self.id = "req_fake_1"
        self.usage = type("U", (), {"prompt_tokens": 11, "completion_tokens": 22})()


class FakeClient:
    """An async Groq client whose `create` returns or raises on a script."""

    def __init__(self, script: list[Any], models: list[str] | None = None,
                 list_error: Exception | None = None):
        self.script = list(script)
        self.payloads: list[dict[str, Any]] = []
        self._models = models or []
        self._list_error = list_error

        transport = self

        class Completions:
            async def create(self, **payload: Any) -> Any:
                transport.payloads.append(payload)
                value = (
                    transport.script.pop(0)
                    if len(transport.script) > 1
                    else transport.script[0]
                )
                if isinstance(value, Exception):
                    raise value
                return value

        class Chat:
            completions = Completions()

        class Models:
            async def list(self) -> Any:
                if transport._list_error:
                    raise transport._list_error
                data = [type("E", (), {"id": name})() for name in transport._models]
                return type("L", (), {"data": data})()

        self.chat = Chat()
        self.models = Models()


@pytest.fixture(autouse=True)
def no_sleeping(monkeypatch):
    """Record the delays instead of waiting for them."""
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr(GroqChatTransport, "_sleep", staticmethod(fake_sleep))
    return slept


def transport(script: list[Any], **over: Any) -> GroqChatTransport:
    kwargs: dict[str, Any] = {"api_key": "not-a-real-key", "client": FakeClient(script)}
    kwargs.update(over)
    return GroqChatTransport(**kwargs)


MESSAGES = [ChatMessage.text("system", "be brief"), ChatMessage.text("user", "a shirt")]


# --- the happy path ----------------------------------------------------------------------


async def test_a_completion_is_unwrapped_with_its_telemetry():
    subject = transport([FakeCompletion('{"ok": true}')])

    result = await subject.complete(model=MODEL, messages=MESSAGES)

    assert result.content == '{"ok": true}'
    assert result.model == MODEL
    assert result.request_id == "req_fake_1"
    assert (result.prompt_tokens, result.completion_tokens) == (11, 22)
    assert result.latency_ms >= 0


async def test_a_schema_becomes_a_strict_json_schema_response_format():
    client = FakeClient([FakeCompletion("{}")])
    subject = GroqChatTransport(api_key="k", client=client)
    schema = SchemaSpec(name="garment", schema={"type": "object"}, description="one garment")

    await subject.complete(model=MODEL, messages=MESSAGES, schema=schema)

    fmt = client.payloads[0]["response_format"]
    assert fmt["type"] == "json_schema"
    assert fmt["json_schema"]["name"] == "garment"
    assert fmt["json_schema"]["strict"] is True
    assert fmt["json_schema"]["schema"] == {"type": "object"}


async def test_no_schema_means_no_response_format_key():
    """Rather than sending an empty one, which some providers reject outright."""
    client = FakeClient([FakeCompletion("{}")])

    await GroqChatTransport(api_key="k", client=client).complete(model=MODEL, messages=MESSAGES)

    assert "response_format" not in client.payloads[0]


async def test_a_single_text_message_is_sent_as_a_plain_string():
    client = FakeClient([FakeCompletion("{}")])

    await GroqChatTransport(api_key="k", client=client).complete(model=MODEL, messages=MESSAGES)

    assert client.payloads[0]["messages"][0] == {"role": "system", "content": "be brief"}


async def test_an_image_part_is_encoded_as_the_provider_expects():
    client = FakeClient([FakeCompletion("{}")])
    messages = [
        ChatMessage(
            role="user",
            content=[
                {"type": "text", "text": "read this"},
                {"type": "image_url", "url": "https://signed.example/x.jpg"},
            ],
        )
    ]

    await GroqChatTransport(api_key="k", client=client).complete(model=MODEL, messages=messages)

    parts = client.payloads[0]["messages"][0]["content"]
    assert parts[0] == {"type": "text", "text": "read this"}
    assert parts[1] == {"type": "image_url", "image_url": {"url": "https://signed.example/x.jpg"}}


# --- error mapping -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raised", "expected"),
    [
        (groq.APITimeoutError(request=REQUEST), ProviderTimeoutError),
        (status_error(groq.RateLimitError, 429), ProviderRateLimitedError),
        (status_error(groq.NotFoundError, 404), ProviderModelMissingError),
        (status_error(groq.AuthenticationError, 401), ProviderRefusedError),
        (status_error(groq.PermissionDeniedError, 403), ProviderRefusedError),
        (status_error(groq.BadRequestError, 400), ProviderRefusedError),
        (status_error(groq.UnprocessableEntityError, 422), ProviderRefusedError),
        (status_error(groq.InternalServerError, 503), ProviderUnavailableError),
        (groq.APIConnectionError(request=REQUEST), ProviderUnavailableError),
    ],
    ids=lambda v: getattr(v, "__name__", type(v).__name__),
)
async def test_every_sdk_exception_maps_to_our_taxonomy(raised, expected):
    subject = transport([raised], max_attempts=1)

    with pytest.raises(expected):
        await subject.complete(model=MODEL, messages=MESSAGES)


async def test_an_unknown_exception_maps_to_unavailable_rather_than_escaping():
    """A vendor exception must never reach the caller: the layers above this one catch
    `ProviderError`, and an unmapped type would sail straight past them."""
    subject = transport([RuntimeError("something new in the SDK")], max_attempts=1)

    with pytest.raises(ProviderUnavailableError):
        await subject.complete(model=MODEL, messages=MESSAGES)


async def test_the_error_message_never_quotes_the_provider():
    """docs/SECURITY-PRIVACY.md. A provider message can echo the request, and the request
    carries text read off a user's photograph — a care label, a slogan, an injected
    sentence. The original stays on __cause__ for a debugger."""
    raised = status_error(groq.BadRequestError, 400)
    subject = transport([raised], max_attempts=1)

    with pytest.raises(ProviderRefusedError) as caught:
        await subject.complete(model=MODEL, messages=MESSAGES)

    assert "provider said no" not in str(caught.value)
    assert caught.value.__cause__ is raised


async def test_the_model_id_is_carried_on_the_error():
    subject = transport([status_error(groq.NotFoundError, 404)], max_attempts=1)

    with pytest.raises(ProviderModelMissingError) as caught:
        await subject.complete(model=MODEL, messages=MESSAGES)

    assert caught.value.model == MODEL
    assert MODEL in caught.value.message


# --- retry -------------------------------------------------------------------------------


async def test_a_retryable_failure_is_retried_then_succeeds(no_sleeping):
    subject = transport(
        [status_error(groq.InternalServerError, 503), FakeCompletion('{"ok": 1}')],
        max_attempts=3,
    )

    result = await subject.complete(model=MODEL, messages=MESSAGES)

    assert result.content == '{"ok": 1}'
    assert len(no_sleeping) == 1


async def test_retries_are_bounded(no_sleeping):
    subject = transport([status_error(groq.InternalServerError, 503)], max_attempts=3)

    with pytest.raises(ProviderUnavailableError):
        await subject.complete(model=MODEL, messages=MESSAGES)

    # Three attempts, two waits between them. Not four.
    assert len(no_sleeping) == 2


async def test_a_refusal_is_not_retried(no_sleeping):
    """Retrying a request the provider called invalid spends the quota twice for the same
    answer, and a bad key will not become a good one."""
    subject = transport([status_error(groq.AuthenticationError, 401)], max_attempts=3)

    with pytest.raises(ProviderRefusedError):
        await subject.complete(model=MODEL, messages=MESSAGES)

    assert no_sleeping == []


async def test_a_deprecated_model_is_not_retried(no_sleeping):
    """The same id cannot start resolving. Moving to the fallback is the analyzer's job."""
    subject = transport([status_error(groq.NotFoundError, 404)], max_attempts=3)

    with pytest.raises(ProviderModelMissingError):
        await subject.complete(model=MODEL, messages=MESSAGES)

    assert no_sleeping == []


async def test_backoff_is_jittered_and_capped(no_sleeping, monkeypatch):
    """Full jitter, not a fixed schedule.

    Several images from one upload hit a rate limit together; a fixed schedule brings them
    all back together too, and the limit is hit again. Asserted by making `random.uniform`
    return its upper bound, so the cap is checkable without depending on a random draw.
    """
    monkeypatch.setattr(groq_transport.random, "uniform", lambda _low, high: high)
    subject = transport([status_error(groq.InternalServerError, 503)], max_attempts=4)

    with pytest.raises(ProviderUnavailableError):
        await subject.complete(model=MODEL, messages=MESSAGES)

    assert no_sleeping == [BACKOFF_BASE_S, BACKOFF_BASE_S * 2, BACKOFF_BASE_S * 4]
    assert all(delay <= MAX_BACKOFF_S for delay in no_sleeping)


async def test_retry_after_is_honoured_but_capped(no_sleeping, monkeypatch):
    """A provider asking for 90 seconds should not hold a request open for 90 seconds."""
    monkeypatch.setattr(groq_transport.random, "uniform", lambda _low, _high: 0.0)
    subject = transport(
        [status_error(groq.RateLimitError, 429, **{"retry-after": "90"})], max_attempts=2
    )

    with pytest.raises(ProviderRateLimitedError):
        await subject.complete(model=MODEL, messages=MESSAGES)

    assert no_sleeping == [MAX_BACKOFF_S]


async def test_a_malformed_retry_after_is_ignored_rather_than_crashing(no_sleeping):
    subject = transport(
        [status_error(groq.RateLimitError, 429, **{"retry-after": "soon"})], max_attempts=1
    )

    with pytest.raises(ProviderRateLimitedError) as caught:
        await subject.complete(model=MODEL, messages=MESSAGES)

    assert caught.value.retry_after_s is None


# --- the transport contract --------------------------------------------------------------


async def test_no_choices_is_a_contract_error_not_a_schema_error():
    """A 200 with no choices means the model never answered. Calling that a schema failure
    would send it down the re-ask path, which cannot help."""
    subject = transport([FakeCompletion("{}", with_choice=False)], max_attempts=1)

    with pytest.raises(ProviderContractError):
        await subject.complete(model=MODEL, messages=MESSAGES)


async def test_empty_content_is_a_contract_error():
    subject = transport([FakeCompletion("")], max_attempts=1)

    with pytest.raises(ProviderContractError):
        await subject.complete(model=MODEL, messages=MESSAGES)


async def test_available_models_returns_ids():
    client = FakeClient([FakeCompletion("{}")], models=["a/one", "b/two", ""])

    ids = await GroqChatTransport(api_key="k", client=client).available_models()

    # The empty id is dropped rather than becoming a model called "".
    assert ids == {"a/one", "b/two"}


async def test_a_failed_model_list_raises_a_provider_error():
    client = FakeClient([], list_error=groq.APIConnectionError(request=REQUEST))

    with pytest.raises(ProviderUnavailableError):
        await GroqChatTransport(api_key="k", client=client).available_models()


def test_the_transport_satisfies_the_protocol():
    from app.adapters.transport import ChatTransport

    assert isinstance(transport([FakeCompletion("{}")]), ChatTransport)
