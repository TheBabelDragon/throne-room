# Web HUD kernel

Portable TypeScript contracts for the Throne Room agent loop.

This is **not** the Grok Build / Vite / TanStack chrome. Those are a host.
These files are the same schemas the Python `agent/` package implements:

| File | Python twin |
|------|-------------|
| `src/schemas.ts` | `agent/schemas.py` |
| `src/engine.ts` | `agent/engine.py` |
| `src/operator-abi.ts` | `agent/operator_abi.py` |
| `src/self-state.ts` | `agent/self_state.py` |
| `src/perception.ts` | `agent/perception.py` |
| `src/memory.ts` | `agent/memory.py` |
| `src/reasoning.ts` | `agent/reason.py` |
| `src/hash.ts` | `agent/hashutil.py` |
| `src/world.ts` | `agent/loop.py` |
| `src/repos.ts` | sibling repo map |
| `src/language-protocol.ts` | `agent/language/protocol.py` |


The live React HUD (chat + lattice + SELF panel) was proven in Grok Build
against this kernel. Drop these modules into any host. Do not put an LLM
inside `engine.ts`.

## HUD

`hud/` is the React operator surface proven against this kernel (chat + lattice + SELF).
Host it in any React app. Live LLM injection is optional via `World.liveReason`.
Do not import a host framework into `src/engine.ts`.
