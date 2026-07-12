"""Event Bus (DD Sec. 2.1.5 / 2.4.3 — *Observer* pattern).

In-process publish/subscribe: a registry mapping event types to lists of
handler callables, populated in the composition root. The publisher does
not know its subscribers; adding a new side effect to an existing event
means adding a new handler, not modifying the use case that publishes it
(Open/Closed principle).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Callable, Type

from ..domain.events import DomainEvent

Handler = Callable[[DomainEvent], None]


class IEventBus(ABC):
    @abstractmethod
    def subscribe(self, event_type: Type[DomainEvent], handler: Handler) -> None: ...

    @abstractmethod
    def publish(self, event: DomainEvent) -> None: ...


class InProcessEventBus(IEventBus):
    def __init__(self):
        self._handlers: dict[type, list[Handler]] = defaultdict(list)

    def subscribe(self, event_type: Type[DomainEvent], handler: Handler) -> None:
        self._handlers[event_type].append(handler)

    def publish(self, event: DomainEvent) -> None:
        for handler in self._handlers[type(event)]:
            handler(event)
