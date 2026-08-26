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
6. Use **New game** to return to color selection.

The browser accepts human moves during the human turn. The LLM uses the CLI during the LLM turn.

## LLM CLI

The LLM should begin with `chess --help` and treat that output as the current command contract. The main commands are:

```text
chess status
chess wait
chess move e7e5
```

`chess move` accepts UCI or SAN notation. UCI examples include `e7e5` and `e7e8q` for promotion. The default move command waits for the human response; add `--no-wait` when an immediate response is required.

In Codex, the bundled `play-llm-chess` skill manages the complete turn loop. Other LLM environments can operate the same game directly through the CLI.

## Game scope

The server keeps one game in memory. The application provides standard legal moves, castling, en passant, promotion, check, checkmate, and draw detection. A server restart starts a fresh setup state.
