---
name: play-llm-chess
description: Play a complete human-vs-LLM chess game through the installed `chess` CLI while the human uses the browser. Use for active LLM Chess games when the user asks Codex to start or continue a browser-vs-CLI match, make the LLM's moves, wait for human turns, or finish the game.
---

# Play LLM Chess

Operate the LLM side of one LLM Chess game through the installed `chess` command. Keep user-facing commentary in the user's language.

## Start or resume

1. Run `chess --help` and treat its output as the current command contract.
2. Query the current game state.
3. If the `chess` command is unavailable, report that LLM Chess must be installed and stop until the command is available.
4. If the server is unreachable, start it in a persistent process. Keep that process running and issue gameplay commands from separate shell calls.
5. When the state is `setup`, tell the human to choose a color in the browser, then wait for the game to reach the LLM's turn.

## Play the game

Handle every returned snapshot by its current state:

- **Terminal state:** Report the result and stop the game loop.
- **Game reset:** Query the current state and continue from it. A reset may return a nonzero process exit even though it is a valid game event.
- **LLM turn:** Choose one move from the current legal-move list, briefly announce it, and submit it with the syntax reported by `chess --help`.
- **Human turn:** Wait for the next human move through the CLI.

Use the default blocking move behavior so one command submits the LLM move and waits for the human response. Switch to nonblocking mode when the user explicitly requests it.

If a blocking command yields a process or session identifier, resume that same process until it returns. Keep one blocking wait active at a time. Continue the turn loop within the same task until the game ends or the user asks to pause.

## Operating rules

- Treat each fresh CLI snapshot and its legal-move list as the sole game-state source.
- Re-evaluate the position after every human move and reset.
- Keep browser color selection and browser move entry human-owned. Provide browser assistance when the user explicitly requests it.
- Choose moves with your own reasoning. Add a chess engine or another model when the user explicitly requests one.
- Keep the server process alive when handing control back to the user.
