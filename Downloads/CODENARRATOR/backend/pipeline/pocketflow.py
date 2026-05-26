"""
PocketFlow — minimalist pipeline engine.
Provides Node, Flow, AsyncFlow, BatchNode, AsyncParallelBatchNode.
"""

import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class Node:
    """Base pipeline node. Subclass and override prep / exec / post."""

    max_retries: int = 1

    def prep(self, shared: dict) -> Any:
        """Read from shared state; return data needed by exec."""
        return None

    def exec(self, prep_result: Any) -> Any:
        """Pure computation. Retried on failure."""
        return None

    def post(self, shared: dict, prep_result: Any, exec_result: Any) -> str:
        """Write results to shared state; return action string."""
        return "default"

    def _exec_with_retry(self, prep_result: Any) -> Any:
        last_exc: Optional[Exception] = None
        for cur_retry in range(self.max_retries):
            try:
                return self.exec(prep_result) if cur_retry == 0 else self._exec_retry(prep_result, cur_retry)
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "%s exec failed (attempt %d/%d): %s",
                    self.__class__.__name__, cur_retry + 1, self.max_retries, exc,
                )
        raise last_exc  # type: ignore[misc]

    def _exec_retry(self, prep_result: Any, cur_retry: int) -> Any:
        """Override in subclasses that need cur_retry awareness (e.g. cache bypass)."""
        return self.exec(prep_result)

    def run(self, shared: dict) -> str:
        prep_result = self.prep(shared)
        exec_result = self._exec_with_retry(prep_result)
        return self.post(shared, prep_result, exec_result)


class AsyncNode(Node):
    """Async variant of Node."""

    async def prep(self, shared: dict) -> Any:  # type: ignore[override]
        return None

    async def exec(self, prep_result: Any) -> Any:  # type: ignore[override]
        return None

    async def post(self, shared: dict, prep_result: Any, exec_result: Any) -> str:  # type: ignore[override]
        return "default"

    async def _exec_with_retry_async(self, prep_result: Any) -> Any:
        last_exc: Optional[Exception] = None
        for cur_retry in range(self.max_retries):
            try:
                if cur_retry == 0:
                    return await self.exec(prep_result)
                else:
                    return await self._exec_retry_async(prep_result, cur_retry)
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "%s async exec failed (attempt %d/%d): %s",
                    self.__class__.__name__, cur_retry + 1, self.max_retries, exc,
                )
        raise last_exc  # type: ignore[misc]

    async def _exec_retry_async(self, prep_result: Any, cur_retry: int) -> Any:
        return await self.exec(prep_result)

    async def run(self, shared: dict) -> str:  # type: ignore[override]
        prep_result = await self.prep(shared)
        exec_result = await self._exec_with_retry_async(prep_result)
        return await self.post(shared, prep_result, exec_result)


class Flow:
    """Synchronous flow executor."""

    def __init__(self, start: Node, transitions: Dict[str, Dict[str, Node]]):
        self.start = start
        self.transitions = transitions

    def run(self, shared: dict) -> None:
        current: Optional[Node] = self.start
        while current is not None:
            node_name = current.__class__.__name__
            logger.info("Running node: %s", node_name)
            action = current.run(shared)
            node_transitions = self.transitions.get(node_name, {})
            current = node_transitions.get(action) or node_transitions.get("default")
            if current is None and action not in ("done", "default", None):
                logger.warning("No transition for action '%s' from node '%s'", action, node_name)


class AsyncFlow(Flow):
    """Asynchronous flow executor."""

    async def run(self, shared: dict) -> None:  # type: ignore[override]
        current: Optional[Node] = self.start
        while current is not None:
            node_name = current.__class__.__name__
            logger.info("Running node: %s", node_name)
            if isinstance(current, AsyncNode):
                action = await current.run(shared)
            else:
                action = current.run(shared)
            node_transitions = self.transitions.get(node_name, {})
            current = node_transitions.get(action) or node_transitions.get("default")
            if current is None and action not in ("done", "default", None):
                logger.warning("No transition for action '%s' from node '%s'", action, node_name)


class BatchNode(Node):
    """Synchronous batch node — processes a list of items."""

    def prep(self, shared: dict) -> List[Any]:  # type: ignore[override]
        return []

    def exec(self, items: List[Any]) -> List[Any]:  # type: ignore[override]
        return [self.exec_item(item) for item in items]

    def exec_item(self, item: Any) -> Any:
        raise NotImplementedError

    def post(self, shared: dict, prep_result: Any, exec_result: Any) -> str:  # type: ignore[override]
        return "default"


class AsyncParallelBatchNode(AsyncNode):
    """Async node that processes items concurrently via asyncio.gather."""

    async def prep(self, shared: dict) -> List[Any]:  # type: ignore[override]
        return []

    async def exec(self, items: List[Any]) -> List[Any]:  # type: ignore[override]
        tasks = [self.exec_item(item) for item in items]
        return await asyncio.gather(*tasks)

    async def exec_item(self, item: Any) -> Any:
        raise NotImplementedError

    async def post(self, shared: dict, prep_result: Any, exec_result: Any) -> str:  # type: ignore[override]
        return "default"
