# LLM Chess

LLM Chess is a local chess workspace where a human plays on a browser board and an LLM submits its moves through a command-line interface. Both sides share one standard chess game managed by the local server.

## Install with an LLM

The recommended setup is to give a shell-capable LLM agent a specific GitHub Release URL from `hehee9/chess-with-llm`. The agent detects the operating system, installs the release wheel with `uv`, configures the optional Codex skill, verifies the CLI, and leaves the local server ready for a game.

Copy this request and replace `<release URL>`:

```text
Install and configure LLM Chess from this GitHub Release: <release URL>. Read INSTALL.md from the same release tag, detect my operating system, preserve unrelated commands and unmanaged skills, verify the CLI, and leave the server ready for a game.
```

The complete agent procedure is in [INSTALL.md](INSTALL.md).

## Start a game

After setup, the local server prints and opens the browser URL. If the server is not already running, start it with:

```text
chess start
```

In the browser:

1. Choose a language. The first visit uses a supported browser language or English, and later visits use the saved selection.
2. Choose **Play White** or **Play Black**.
3. Move by clicking a piece and its destination, or by dragging the piece.
4. Choose a queen, rook, bishop, or knight when promoting a pawn.
5. Follow the turn, last move, and move history in the side rail.
6. Use **Take back** to request a takeback of your latest move. The takeback is applied when the opponent accepts.
7. Use **Resign** to end the game immediately.
8. Use **New game** to return to color selection.

## LLM CLI

The LLM should begin with `chess --help` and treat that output as the current command contract. The main commands are:

```text
chess status
chess wait
chess move e7e5
chess takeback request
chess takeback accept
chess takeback reject
chess resign
```

`chess move` accepts UCI or SAN notation. UCI examples include `e7e5` and `e7e8q` for promotion. The default move command waits for the human response; add `--no-wait` when an immediate response is required.

`chess takeback request` requests a takeback of the LLM's latest move and waits until the human accepts or rejects it. Respond to a human takeback request with `chess takeback accept` or `chess takeback reject`. `chess resign` ends the game immediately.

In Codex, the bundled `play-llm-chess` skill manages the complete turn loop. Other LLM environments can operate the same game directly through the CLI.

## Game scope

The server keeps one game in memory. The application provides standard legal moves, castling, en passant, promotion, check, checkmate, draw detection, mutual takeback requests, and resignation. A server restart starts a fresh setup state.

## License

LLM Chess is licensed under the [GNU General Public License v3.0 or later](LICENSE).
