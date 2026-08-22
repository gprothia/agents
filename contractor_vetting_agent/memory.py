"""Context Bloat Management, History Compaction, and Async Memory Consolidation.

Implements:
1. HistoryCompactor: Token-aware sliding window and conversational summarization.
2. AsyncMemoryManager: Non-blocking background worker for memory consolidation and indexing.
"""

import asyncio
import threading
import time
from typing import Any, Callable, Dict, List, Optional
from datetime import datetime, timezone

from .storage import storage
from .telemetry import PIIRedactionService, get_structured_logger

logger = get_structured_logger("contractor_vetting.memory")


# ==============================================================================
# HISTORY COMPACTOR (Context Bloat Management)
# ==============================================================================

class HistoryCompactor:
    """Manages context window bloat via sliding windows and executive summarization."""

    def __init__(self, max_raw_turns: int = 6, max_estimated_tokens: int = 4000):
        self.max_raw_turns = max_raw_turns
        self.max_estimated_tokens = max_estimated_tokens

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Heuristic estimation of token count (~4 characters per token)."""
        return max(1, len(text) // 4)

    def compact_history(
        self,
        session_id: str,
        turns: List[Dict[str, Any]],
        existing_summary: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Compact conversation turns into an executive summary + recent raw turns."""
        if not turns:
            return []

        # If turn count is within limits, return as is
        if len(turns) <= self.max_raw_turns:
            return turns

        # Partition into older turns to summarize and recent turns to keep raw
        older_turns = turns[:-self.max_raw_turns]
        recent_turns = turns[-self.max_raw_turns:]

        # Build compact summary of older turns
        summary_points = []
        if existing_summary:
            summary_points.append(f"PREVIOUS CONTEXT: {existing_summary}")

        summary_points.append("COMPACTED PRIOR VETTING STAGES:")
        for t in older_turns:
            role = t.get("role", "unknown")
            content = t.get("content", "")
            # Truncate large tool outputs in summary
            snippet = content[:180] + "..." if len(content) > 180 else content
            summary_points.append(f"  [{role.upper()}]: {snippet}")

        compacted_summary_text = "\n".join(summary_points)

        # Update storage session summary asynchronously or directly
        storage.update_session_summary(session_id, compacted_summary_text)

        logger.info(
            f"History compacted for session '{session_id}': {len(older_turns)} older turns summarized.",
            extra={"session_id": session_id, "older_turns_count": len(older_turns), "recent_turns_count": len(recent_turns)}
        )

        compacted_history = [
            {
                "role": "system",
                "content": f"[SYSTEM MEMORY SUMMARY OF PRIOR TURNS]:\n{compacted_summary_text}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ] + recent_turns

        return compacted_history


# ==============================================================================
# ASYNC MEMORY OPERATIONS (Non-Blocking Background Consolidation)
# ==============================================================================

class AsyncMemoryManager:
    """Non-blocking background memory manager for expensive consolidation and indexing."""

    _queue: Optional[asyncio.Queue] = None
    _worker_task: Optional[asyncio.Task] = None
    _thread_worker: Optional[threading.Thread] = None
    _stop_event = threading.Event()

    @classmethod
    def schedule_background_consolidation(
        cls,
        session_id: str,
        contractor_id: str,
        turn_data: Dict[str, Any],
        callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        """Schedule an asynchronous background memory update without blocking the user response."""
        task_payload = {
            "session_id": session_id,
            "contractor_id": contractor_id,
            "turn_data": PIIRedactionService.redact_data(turn_data),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Spawn in daemon thread or event loop
        def _background_worker():
            try:
                # Simulate expensive embedding computation or Vertex Search vector indexing
                time.sleep(0.05)
                # Persist turn in storage
                storage.save_turn(
                    session_id=session_id,
                    role=turn_data.get("role", "user"),
                    content=turn_data.get("content", ""),
                    tool_calls=turn_data.get("tool_calls"),
                )
                logger.debug(f"Background memory indexed for session {session_id} and contractor {contractor_id}")
                if callback:
                    callback(task_payload)
            except Exception as ex:
                logger.error(f"Error during async memory consolidation: {ex}", exc_info=True)

        worker_thread = threading.Thread(target=_background_worker, daemon=True)
        worker_thread.start()


# Global history compactor instance
compactor = HistoryCompactor()
