# Memory Routing Research Summary

Sources: MemGPT/Letta, Zep, LangGraph Memory, Claude memory system, cognitive science literature. Compiled 2026-05-03.

## MemGPT/Letta: Core vs Archival

- **Core memory**: Two fixed blocks (`human`, `persona`). Always in system prompt. ~2-4KB budget.
- **Archival memory**: Unlimited vector store. Accessed only via `archival_memory_insert`/`archival_memory_search`. Never in context unless explicitly retrieved.
- **Routing enforced at tool level**: Agent cannot write to core memory except through `core_memory_append`/`core_memory_replace`. System prompt restricts core to "essential identity/preference" data.
- **Key quote**: "Core memory should be short — think of it as the agent's sticky note, not its filing cabinet."

## Zep: Pre-Write Classification

- **Memory Inspector** classifies before routing:
  - Identity → core
  - Preference → core
  - Episode → episodic store (on-demand, auto-summarized after 7 days)
  - Relationship → semantic graph (on-demand)
- Entity-centric deduplication: new fact updates existing rather than appending.
- Auto-summarization reduces old episodic data by ~90%.

## LangGraph Memory: Namespace Enforcement

- Store uses namespaces: `("user_id", "preferences")` for always-on, `("user_id", "facts")` for on-demand.
- System prompt explicitly references namespace structure, making routing part of the prompt.
- Metadata filtering allows selective loading (e.g., only preference-type data into context).

## Claude: Budget-Constrained Memory Manager

- Lightweight "memory manager" tool runs each turn: create/read/update.
- Three tiers: identity facts (always), interaction preferences (always), episodic facts (on-demand by relevance).
- **Token budget** per turn for memory injection — hard constraint against always-on bloat.

## Cognitive Science

- **Miller's Law**: ~7±2 chunks in working memory. Overloading degrades instruction-following.
- **Baddeley**: Working memory is for manipulation, not storage. If not actively reasoning about a fact this turn, it shouldn't be in always-on.
- **Cowan**: Capacity actually ~3-4 chunks. Overloading causes proactive interference.
- **Ericsson & Kintsch (1995) "Long-Term Working Memory"**: Experts create retrieval cues in working memory pointing to long-term storage — not the facts themselves. This is exactly what MEMORY.md should be: cues pointing to fact_store.

## Hermes Implementation Mapping

| Theory/Framework | Hermes Layer |
|---|---|
| MemGPT Core Memory | MEMORY.md |
| MemGPT Archival Memory | fact_store |
| Zep Procedural Store | Skills (SKILL.md) |
| Zep Episodic Store | session_search |
| LangGraph Store namespaces | fact_store categories + tags |
| Retrieval cues (Ericsson) | One-line pointers in MEMORY.md |

## Failure Modes from Always-On Pollution

1. **Context window poisoning**: Always-on grows to 10K+ tokens, model starts ignoring system instructions.
2. **Fact conflation**: Adjacent unrelated facts → hallucinated relationships.
3. **Priority inversion**: Low-value episodic facts displace high-value rules.
4. **Amnesia cascade**: Truncation cuts system instructions first when context overflows.
5. **Update conflicts**: Duplicate contradictory facts without dedup → inconsistent behavior.