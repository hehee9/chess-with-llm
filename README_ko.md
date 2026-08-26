# LLM Chess

LLM Chess는 사람이 브라우저 보드에서 대국하고 LLM이 CLI로 수를 전달하는 로컬 체스 작업대입니다. 양측은 로컬 서버가 관리하는 하나의 표준 체스 게임을 함께 공유합니다.

## LLM으로 설치하기

권장 설치 방법은 셸 실행 권한이 있는 LLM 에이전트에게 `hehee9/chess-with-llm`의 GitHub Release URL을 제공하는 것입니다. 에이전트가 운영체제를 감지하고, `uv`를 사용해 릴리스 wheel 파일을 설치하며, 선택 사항인 Codex 스킬을 설정하고 CLI를 검증한 뒤 로컬 서버를 대국 가능한 상태로 준비합니다.

다음 요청문을 복사한 뒤 `<release URL>` 부분을 변경하여 사용하세요:

```text
Install and configure LLM Chess from this GitHub Release: <release URL>. Read INSTALL.md from the same release tag, detect my operating system, preserve unrelated commands and unmanaged skills, verify the CLI, and leave the server ready for a game.
```

에이전트의 전체 설치 절차는 [INSTALL.md](INSTALL.md)에서 확인할 수 있습니다.

## 게임 시작하기

설치 후 로컬 서버가 브라우저 URL을 출력하고 자동으로 엽니다. 서버가 아직 실행 중이지 않다면 다음 명령어로 시작하세요:

```text
chess start
```

브라우저에서:

1. 언어를 선택합니다. 처음 방문하면 지원되는 브라우저 언어 또는 English를 사용하고, 이후에는 저장된 선택을 사용합니다.
2. **백으로 플레이** 또는 **흑으로 플레이**를 선택합니다.
3. 말을 클릭한 뒤 이동할 위치를 클릭하거나, 말을 드래그하여 이동합니다.
4. 폰 승진 시 퀸, 룩, 비숍, 나이트 중 하나를 선택합니다.
5. 사이드 레일에서 현재 차례, 마지막 수, 수순 기록을 확인합니다.
6. **새 대국**을 눌러 색상 선택으로 돌아갈 수 있습니다.

사람 차례에는 브라우저에서 사람의 수를 입력받습니다. LLM 차례에는 LLM이 CLI를 사용합니다.

## LLM CLI

LLM은 `chess --help`로 시작하여 해당 출력을 현재 명령어 규약으로 취급해야 합니다. 주요 명령어는 다음과 같습니다:

```text
chess status
chess wait
chess move e7e5
```

`chess move`는 UCI 또는 SAN 표기법을 지원합니다. UCI 표기법 예시로는 `e7e5` 및 승진 시 `e7e8q` 등이 있습니다. 기본 이동 명령어는 사람의 응답을 기다리며, 즉각적인 반환이 필요한 경우 `--no-wait`를 추가합니다.

Codex에서는 기본 제공되는 `play-llm-chess` 스킬이 전체 턴 루프를 관리합니다. 다른 LLM 환경에서는 CLI를 통해 동일한 게임을 직접 조작할 수 있습니다.

## 게임 범위

서버는 메모리에 하나의 게임만 유지합니다. 애플리케이션은 표준 규칙에 따른 합법적인 이동, 캐슬링, 앙파상, 승진, 체크, 체크메이트 및 무승부 감지 기능을 제공합니다. 서버를 재시작하면 새로운 준비(setup) 상태로 시작됩니다.
