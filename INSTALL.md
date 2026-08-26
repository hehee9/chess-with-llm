# Install LLM Chess

This guide is an execution contract for an LLM agent with internet, shell, and user-level filesystem access. The user supplies a specific GitHub Release URL from `hehee9/chess-with-llm`. Complete the installation without requiring the user to choose commands for their operating system.

## Completion criteria

Finish when all applicable conditions are true:

- The release wheel is installed as a user-level `uv` tool.
- The installed `chess` executable passes `<chess executable> --help`.
- A Codex environment has the bundled `play-llm-chess` skill installed safely.
- The LLM Chess server is running, and a separate `<chess executable> status` call reports `setup` for a new server or the preserved state of an existing LLM Chess game.
- The browser page is available at the URL printed by `<chess executable> start`.

## 1. Validate the release

1. Resolve the supplied URL to a specific release tag. Confirm that it uses HTTPS and belongs to:

   ```text
   github.com/hehee9/chess-with-llm/releases/
   ```

2. Read `INSTALL.md` from the same repository tag:

   ```text
   https://github.com/hehee9/chess-with-llm/blob/<release tag>/INSTALL.md
   ```

   Use that tagged guide for the rest of the installation so the instructions match the selected release.

3. Inspect that release and select the single asset matching:

   ```text
   llm_chess-*-py3-none-any.whl
   ```

4. Download the wheel to a temporary directory. Stop and report the problem when the repository does not match, the wheel is missing, or more than one wheel matches.

## 2. Ensure `uv` is available

1. Run `uv --version`.
2. When `uv` is unavailable, detect the operating system and shell, then install it with the current user-level method from the [official uv installation guide](https://docs.astral.sh/uv/getting-started/installation/).
3. Resolve the installed `uv` executable directly when the current shell has not reloaded its updated `PATH`.
4. Run `uv --version` again before continuing.

`uv` manages the required Python runtime. A separate system Python installation is not required.

## 3. Install the CLI

1. Use the current shell's command-discovery mechanism to check for an existing `chess` command and resolve its executable path.
2. When a `chess` command exists, inspect its path and `--help` output. Continue only when its ownership as LLM Chess is established. Preserve any unrelated or unidentified command and report the conflict.
3. Run `uv tool list` and inspect any existing tool that provides a `chess` executable. Do not use `--force` to replace an executable owned by another tool.
4. Install the downloaded wheel:

   ```text
   uv tool install <absolute path to the downloaded wheel>
   ```

5. Get the tool executable directory:

   ```text
   uv tool dir --bin
   ```

6. If that directory is not on the user's `PATH`, run:

   ```text
   uv tool update-shell
   ```

7. Resolve the installed executable's absolute path inside the tool executable directory. The executable is named `chess` on macOS and Linux and `chess.exe` on Windows. Record that path as `<chess executable>` and use it for every remaining command in the current installation task.
8. Verify the installed interface:

   ```text
   <chess executable> --help
   ```

Treat the help output as the current CLI contract.

## 4. Install the Codex skill when applicable

Perform this section when running inside Codex or when the user explicitly requests Codex integration. Other LLM environments use the installed CLI directly.

1. Resolve the Codex home directory:
   - Use `CODEX_HOME` when it is set.
   - Otherwise use `.codex` inside the user's home directory.
2. Run `uv tool dir` and search that tool directory for this packaged file:

   ```text
   llm_chess/skills/play-llm-chess/SKILL.md
   ```

3. Use the parent `play-llm-chess` directory as the skill source. It must contain:

   ```text
   SKILL.md
   agents/openai.yaml
   ```

4. Set the destination and adjacent ownership marker:

   ```text
   <CODEX_HOME>/skills/play-llm-chess
   <CODEX_HOME>/skills/play-llm-chess.llm-chess-managed
   ```

   The marker content is:

   ```text
   llm-chess:play-llm-chess
   ```

5. Apply these ownership rules:
   - When the destination exists without the exact marker, preserve it and report that Codex skill installation was skipped because the existing skill is unmanaged.
   - When the destination and exact marker both exist, prepare and validate a sibling staging copy before replacing the managed destination.
   - When the destination is absent, prepare and validate a sibling staging copy before moving it into place and writing the marker.
   - Restore the previous managed destination when replacement fails.
6. Confirm that the installed skill contains `SKILL.md` and `agents/openai.yaml`.
7. Tell the user to open a new Codex task so Codex can discover the newly installed skill.

## 5. Start and verify the server

1. Start the server with the resolved `chess` executable in a persistent process:

   ```text
   <chess executable> start
   ```

2. Keep that process running and issue verification commands from a separate shell process.
3. Run:

   ```text
   <chess executable> status
   ```

4. For a newly started server, confirm that the output contains:

   ```text
   **Status:** `setup`
   ```

5. Confirm that the browser page responds at the local URL printed by `chess start`.
6. Leave the server running so the user can choose a color and begin the game.

If an existing LLM Chess server already has an active game, preserve that game and report its current status. If another application occupies the required local address, report the conflict without stopping that application.

## Installation report

Report these results to the user:

- Release tag and wheel asset
- Installed `chess` executable path
- `chess --help` verification result
- Codex skill installation, skip, or conflict status
- Server URL and game status
