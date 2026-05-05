"""Тесты для EventBus и Event."""

import pytest

from app.core.events import EventBus, Event


class DummyEvent(Event):
    """Тестовое событие."""

    event_type = "dummy"


class AnotherDummyEvent(Event):
    """Другое тестовое событие."""

    event_type = "another_dummy"


@pytest.mark.asyncio
async def test_subscribe_and_publish() -> None:
    """Тест базовой подписки и публикации."""
    bus = EventBus()
    calls = []

    async def handler(event: Event) -> None:
        calls.append(event)

    bus.subscribe(DummyEvent, handler)
    event = DummyEvent()
    await bus.publish(event)

    assert len(calls) == 1
    assert calls[0] is event


@pytest.mark.asyncio
async def test_publish_without_subscribers() -> None:
    """Тест публикации без подписчиков не падает."""
    bus = EventBus()
    event = DummyEvent()
    await bus.publish(event)  # Не должно падать


@pytest.mark.asyncio
async def test_multiple_subscribers_fifo_order() -> None:
    """Тест порядка вызова подписчиков (FIFO)."""
    bus = EventBus()
    calls = []

    async def handler1(event: Event) -> None:
        calls.append(1)

    async def handler2(event: Event) -> None:
        calls.append(2)

    async def handler3(event: Event) -> None:
        calls.append(3)

    bus.subscribe(DummyEvent, handler1)
    bus.subscribe(DummyEvent, handler2)
    bus.subscribe(DummyEvent, handler3)

    await bus.publish(DummyEvent())

    assert calls == [1, 2, 3]


@pytest.mark.asyncio
async def test_subscriber_error_does_not_interrupt_others() -> None:
    """Тест изоляции ошибки одного подписчика."""
    bus = EventBus()
    calls = []

    async def failing_handler(event: Event) -> None:
        calls.append("failing")
        raise RuntimeError("Ошибка в подписчике")

    async def working_handler(event: Event) -> None:
        calls.append("working")

    bus.subscribe(DummyEvent, failing_handler)
    bus.subscribe(DummyEvent, working_handler)

    await bus.publish(DummyEvent())

    assert calls == ["failing", "working"]


@pytest.mark.asyncio
async def test_subscribe_to_different_event_types() -> None:
    """Тест подписки на разные типы событий."""
    bus = EventBus()
    test_calls = []
    another_calls = []

    async def test_handler(event: Event) -> None:
        test_calls.append(event)

    async def another_handler(event: Event) -> None:
        another_calls.append(event)

    bus.subscribe(DummyEvent, test_handler)
    bus.subscribe(AnotherDummyEvent, another_handler)

    await bus.publish(DummyEvent())
    await bus.publish(AnotherDummyEvent())

    assert len(test_calls) == 1
    assert len(another_calls) == 1
    assert isinstance(test_calls[0], DummyEvent)
    assert isinstance(another_calls[0], AnotherDummyEvent)


@pytest.mark.asyncio
async def test_subscribe_non_event_type_raises() -> None:
    """Тест подписки на не-Event тип вызывает TypeError."""
    bus = EventBus()

    async def handler(event: Event) -> None:
        pass

    with pytest.raises(TypeError):
        bus.subscribe(str, handler)  # type: ignore[arg-type]
