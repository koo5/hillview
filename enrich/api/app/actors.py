"""Remoulade wiring (API side = producer only). Cribbed from the accounts-assessor
tasking.py, minus result/state backends: workers are UNTRUSTED in the topology sense —
they consume from RabbitMQ and report back over HTTP with a token, never touching the
DBs. The matcher worker (enrich/matcher/worker.py, host-side venv with torch+MASt3R)
declares the same actor by name and executes it."""
import os

import remoulade
from remoulade.brokers.rabbitmq import RabbitmqBroker

_ready = False


@remoulade.actor(queue_name="matching")
def match_pair(payload: dict) -> None:
    """Executed by the matcher worker; the API only .send()s it."""
    raise NotImplementedError("producer-side stub")


def init_broker() -> bool:
    """Lazy: the API works fine without a broker (candidates/verdicts don't need it);
    only enqueueing does."""
    global _ready
    if _ready:
        return True
    url = os.getenv("RABBITMQ_URL")
    if not url:
        return False
    broker = RabbitmqBroker(url=f"amqp://{url}?timeout=15", confirm_delivery=True)
    remoulade.set_broker(broker)
    remoulade.declare_actors([match_pair])
    _ready = True
    return True
