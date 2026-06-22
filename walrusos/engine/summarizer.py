import re
from typing import List, Dict, Any, Tuple
from walrusos.core.models.memory import MemoryEvent

class MemorySummarizer:
    """
    Automatically distills long histories into dense checkpoints to save LLM tokens.
    """
    
    @staticmethod
    def _extract_first_sentence(text: str) -> str:
        """Extract the first sentence from a block of text."""
        match = re.search(r'([^.!?]+[.!?])', text)
        if match:
            return match.group(1).strip()
        return text.strip()

    def summarize_session(self, events_with_payloads: List[Tuple[MemoryEvent, Dict[str, Any]]]) -> str:
        """
        Extractive summarizer: takes the first sentence of each event payload's string representation,
        deduplicates them, and joins them.
        """
        sentences = []
        seen = set()
        for _, payload in events_with_payloads:
            # We strip internal meta before summarizing if needed, or just dump values
            text = " ".join(str(v) for k, v in payload.items() if not k.startswith("_") and isinstance(v, (str, int, float)))
            if not text:
                continue
            first_sentence = self._extract_first_sentence(text)
            if first_sentence and first_sentence not in seen:
                seen.add(first_sentence)
                sentences.append(first_sentence)
                
        return " ".join(sentences)

    async def create_checkpoint(self, stream, label: str) -> str:
        """
        Pulls the latest un-checkpointed events, summarizes them, and appends a new event.
        stream is a StreamClient instance.
        """
        # Find the last checkpoint to only summarize recent events
        # In a full implementation we'd use MemorySearch, here we'll just grab the recent timeline
        timeline = await stream.timeline()
        recent_events = []
        for ev, p in reversed(timeline):
            if getattr(ev, "memory_type", None) == "summary" and "checkpoint" in getattr(ev, "tags", []):
                break
            recent_events.append((ev, p))
            
        recent_events.reverse() # Restore chronological order
        
        if not recent_events:
            return ""
            
        summary_text = self.summarize_session(recent_events)
        if not summary_text:
            return ""
            
        # We append a new summary event using the stream client
        event = await stream.append(
            {"checkpoint_summary": summary_text, "label": label},
            memory_type="summary",
            importance=1.0,
            tags=["checkpoint", label]
        )
        return getattr(event, "id", getattr(event, "event_id", ""))

    async def auto_checkpoint(self, stream, every_n_events: int = 50) -> None:
        """
        Checks the current epoch since the last checkpoint, triggering one if the threshold is crossed.
        """
        # Simple implementation: if total timeline length modulo every_n_events == 0
        # More robust implementation would track epoch delta since last checkpoint
        timeline = await stream.timeline()
        total_events = len(timeline)
        
        if total_events > 0 and total_events % every_n_events == 0:
            label = f"Auto-checkpoint at event {total_events}"
            await self.create_checkpoint(stream, label)
