---
name: play-llm-chess
description: Play a complete human-vs-LLM chess game through the installed `chess` CLI while the human uses the browser, including takeback requests and resignation. Use for active LLM Chess games when the user asks Codex to start or continue a browser-vs-CLI match, make the LLM's moves, wait for human turns, or finish the game.
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

- **Terminal state:** Treat checkmate, draw, and a snapshot with `status: resigned` as terminal. The corresponding `human_resigned` or `llm_resigned` event identifies who resigned. Report the result and stop the game loop. The takeback events `takeback_requested`, `takeback_accepted`, and `takeback_rejected` are control events; handle them before deciding the next turn.
- **Game reset:** Query the current state and continue from it. A reset may return a nonzero process exit even though it is a valid game event.
- **Human takeback request:** A `takeback_requested` event can wake `chess wait` or a blocking `chess move`. All moves are frozen while the request is pending. Decide whether to accept or reject the request, then run exactly one of `chess takeback accept` or `chess takeback reject` and handle the returned snapshot. Do not invent an acceptance policy or make this decision outside the tool loop.
- **Takeback accepted:** For a `takeback_accepted` event, use the returned snapshot as the sole source of truth. If the requester's move was still the last move, the position rewinds one ply; if the opponent had already replied, it rewinds two plies so the requester moves again.
- **Takeback rejected:** For a `takeback_rejected` event, the position and move history remain unchanged. Re-evaluate the returned snapshot and continue the normal turn loop.
- **LLM turn:** Choose one move from the current legal-move list, briefly announce it, and submit it with the syntax reported by `chess --help`.
- **Human turn:** Wait for the next human move through the CLI.

Use the default blocking move behavior so one command submits the LLM move and waits for the human response. Switch to nonblocking mode when the user explicitly requests it.

The LLM may request a takeback of its own latest move with `chess takeback request`. That command blocks until the human accepts or rejects the request. Resume the same process when a session identifier is returned, then handle the `takeback_accepted`, `takeback_rejected`, or resignation terminal event before continuing. If the LLM is instructed to resign, run `chess resign`; either side's resignation is immediately terminal.

If a blocking command yields a process or session identifier, resume that same process until it returns. Keep one blocking wait active at a time. Continue the turn loop within the same task until the game ends or the user asks to pause.

## Operating rules

- Treat each fresh CLI snapshot and its legal-move list as the sole game-state source.
- Re-evaluate the position after every human move and reset.
- Handle a human takeback request returned by either `chess wait` or a blocking `chess move` before issuing another move command.
- Keep the server process alive throughout moves, takeback requests, responses, and terminal results so the human can start a new game afterward.
- Keep browser color selection and browser move entry human-owned. Provide browser assistance when the user explicitly requests it.
- Choose moves with your own reasoning. Add a chess engine or another model when the user explicitly requests one.
