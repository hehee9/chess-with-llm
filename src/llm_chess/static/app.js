/**
 * @file LLM Chess 브라우저 작업대
 * @description 서버가 보낸 한 판의 상태를 표시하고 사람의 UCI 수만 전송합니다.
 */

const PIECE_GLYPHS = {
  K: "♔",
  Q: "♕",
  R: "♖",
  B: "♗",
  N: "♘",
  P: "♙",
  k: "♚",
  q: "♛",
  r: "♜",
  b: "♝",
  n: "♞",
  p: "♟",
};

const i18n = window.LlmChessI18n;

const PIECE_TYPES = {
  k: "king",
  q: "queen",
  r: "rook",
  b: "bishop",
  n: "knight",
  p: "pawn",
};

const PROMOTION_TYPES = {
  q: "queen",
  r: "rook",
  b: "bishop",
  n: "knight",
};

const STATUS_REASON_KEYS = {
  checkmate: "statusReason.checkmate",
  stalemate: "statusReason.stalemate",
  insufficient_material: "statusReason.insufficient_material",
  seventyfive_moves: "statusReason.seventyfive_moves",
  fivefold_repetition: "statusReason.fivefold_repetition",
  fifty_moves: "statusReason.fifty_moves",
  threefold_repetition: "statusReason.threefold_repetition",
};

const initialSnapshot = {
  event: "setup",
  game_id: null,
  revision: 0,
  status: "setup",
  status_reason: "no_game",
  human_color: null,
  llm_color: null,
  turn: null,
  fen: null,
  pieces: {},
  legal_moves: [],
  move_history: [],
  last_move: null,
  check: false,
  checked_king_square: null,
  result: null,
};

const ui = {
  snapshot: initialSnapshot,
  setupOpen: true,
  requestPending: false,
  selectedSquare: null,
  promotionMoves: [],
  setupReturnFocus: null,
  connection: "connecting",
  error: null,
};

const elements = {
  appShell: document.querySelector("#app-shell"),
  topbar: document.querySelector(".topbar"),
  workspace: document.querySelector(".workspace"),
  board: document.querySelector("#chessboard"),
  boardCaption: document.querySelector("#board-caption"),
  boardStatus: document.querySelector("#board-status"),
  statusDot: document.querySelector("#status-dot"),
  revisionLabel: document.querySelector("#revision-label"),
  matchId: document.querySelector("#match-id"),
  clockFace: document.querySelector("#clock-face"),
  clockLabel: document.querySelector("#clock-label"),
  clockValue: document.querySelector("#clock-value"),
  clockDetail: document.querySelector("#clock-detail"),
  liveIndicator: document.querySelector("#live-indicator"),
  lastMoveValue: document.querySelector("#last-move-value"),
  lastMoveMeta: document.querySelector("#last-move-meta"),
  moveList: document.querySelector("#move-list"),
  moveCount: document.querySelector("#move-count"),
  emptyHistory: document.querySelector("#empty-history"),
  connectionValue: document.querySelector("#connection-value"),
  errorCopy: document.querySelector("#error-copy"),
  setupLayer: document.querySelector("#setup-layer"),
  setupError: document.querySelector("#setup-error"),
  newGameButton: document.querySelector("#new-game-button"),
  promotionDialog: document.querySelector("#promotion-dialog"),
  promotionOptions: document.querySelector("#promotion-options"),
  promotionCancel: document.querySelector("#promotion-cancel"),
  colorButtons: document.querySelectorAll("[data-color]"),
  localeSelects: document.querySelectorAll("[data-locale-select]"),
};




/* =================================== 다국어 표시 =================================== */


/** @description 정적 HTML 문구와 접근성 라벨을 현재 카탈로그로 갱신합니다. */
function applyStaticCopy() {
  document.querySelectorAll("[data-i18n]").forEach((element) => {
    element.textContent = i18n.t(element.dataset.i18n);
  });
  document.querySelectorAll("[data-i18n-aria-label]").forEach((element) => {
    element.setAttribute("aria-label", i18n.t(element.dataset.i18nAriaLabel));
  });
  syncLocaleControls();
}

/** @description 두 언어 선택기의 선택값을 동일한 로케일로 맞춥니다. */
function syncLocaleControls() {
  const locale = i18n.getLocale();
  elements.localeSelects.forEach((select) => {
    select.value = locale;
  });
}

/** @description 카탈로그 오류와 연결 오류를 다시 번역할 수 있는 상태로 만듭니다. */
function localizedErrorState(error, fallbackKey) {
  return error && error.i18n ? error.i18n : { key: fallbackKey, values: {} };
}

/** @description 현재 오류 상태를 선택된 언어의 문구로 바꿉니다. */
function errorText() {
  if (!ui.error) {
    return "";
  }
  const values = ui.error.values.actorKey
    ? { actor: i18n.t(ui.error.values.actorKey) }
    : ui.error.values;
  return i18n.t(ui.error.key, values);
}

/** @description 서버 기물 기호를 현재 언어의 기물 이름으로 바꿉니다. */
function pieceName(piece) {
  const color = piece === piece.toUpperCase() ? "white" : "black";
  return i18n.t(`piece.${color}.${PIECE_TYPES[piece.toLowerCase()]}`);
}

/** @description 승진 기호를 현재 언어의 기물 이름으로 바꿉니다. */
function promotionName(promotion) {
  return i18n.t(`promotion.${PROMOTION_TYPES[promotion.toLowerCase()]}`);
}




/* =================================== 서버 통신 =================================== */


/** @description JSON 응답을 확인하고 서버 오류의 detail을 전달합니다. */
async function requestJson(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const payload = await response.json();
  if (!response.ok) {
    throw i18n.serverError(payload.detail);
  }
  return payload;
}

/** @description 초기 게임 상태를 불러옵니다. */
async function loadState() {
  try {
    const snapshot = await requestJson("/api/state");
    applySnapshot(snapshot);
    ui.connection = "connected";
    ui.error = null;
    ui.setupOpen = snapshot.game_id === null;
    render();
  } catch (error) {
    ui.connection = "error";
    ui.error = localizedErrorState(error, "error.connect");
    render();
  }
}

/** @description SSE로 전달된 전체 스냅샷을 화면에 적용합니다. */
function handleServerEvent(event) {
  try {
    const snapshot = JSON.parse(event.data);
    applySnapshot(snapshot);
    ui.connection = "connected";
    ui.error = null;
    render();
  } catch (error) {
    ui.connection = "error";
    ui.error = localizedErrorState(error, "error.state");
    render();
  }
}




/* =================================== 상태와 표시 =================================== */


/** @description 서버 스냅샷을 현재 화면 상태로 교체합니다. */
function applySnapshot(snapshot) {
  ui.snapshot = snapshot;
  ui.selectedSquare = null;
  ui.promotionMoves = [];
  if (snapshot.game_id === null) {
    ui.setupOpen = true;
  }
}

/** @description 사람 차례에만 브라우저 수를 허용합니다. */
function canHumanMove() {
  const snapshot = ui.snapshot;
  return Boolean(snapshot.game_id)
    && snapshot.status === "active"
    && snapshot.turn === "human"
    && !ui.requestPending
    && ui.connection === "connected";
}

/** @description 색상 이름을 현재 언어로 표시합니다. */
function colorName(color) {
  return i18n.t(color === "black" ? "color.black" : "color.white");
}

/** @description 서버 종료 사유를 현재 언어의 상태 문구로 바꿉니다. */
function statusReasonText() {
  const key = STATUS_REASON_KEYS[ui.snapshot.status_reason];
  return key ? i18n.t(key) : i18n.t(ui.snapshot.status === "checkmate" ? "statusReason.checkmate" : "statusReason.unknownDraw");
}

/** @description 현재 게임의 읽기 쉬운 상태 문구를 만듭니다. */
function statusText() {
  const snapshot = ui.snapshot;
  if (ui.connection === "error") {
    return i18n.t("status.connectionError");
  }
  if (ui.connection === "disconnected") {
    return i18n.t("status.disconnected");
  }
  if (ui.error) {
    return i18n.t("status.requestError");
  }
  if (snapshot.game_id === null || snapshot.status === "setup") {
    return i18n.t("status.setup");
  }
  if (snapshot.status === "checkmate") {
    return statusReasonText();
  }
  if (snapshot.status === "draw") {
    return statusReasonText();
  }
  if (snapshot.check) {
    return i18n.t(snapshot.turn === "human" ? "status.checkHuman" : "status.checkLlm");
  }
  if (snapshot.turn === "human") {
    return i18n.t("status.human");
  }
  return i18n.t("status.llm");
}

/** @description 시계 면의 큰 상태와 보조 설명을 갱신합니다. */
function renderClock() {
  const snapshot = ui.snapshot;
  let tone = "setup";
  let label = i18n.t("clock.setup.label");
  let value = i18n.t("clock.setup.value");
  let detail = i18n.t("clock.setup.detail");

  if (ui.connection === "error") {
    tone = "error";
    label = i18n.t("clock.error.label");
    value = i18n.t("clock.error.value");
    detail = i18n.t("clock.error.detail");
  } else if (ui.connection === "disconnected") {
    tone = "terminal";
    label = i18n.t("clock.disconnected.label");
    value = i18n.t("clock.disconnected.value");
    detail = i18n.t("clock.disconnected.detail");
  } else if (ui.error) {
    tone = "error";
    label = i18n.t("clock.requestError.label");
    value = i18n.t("clock.requestError.value");
    detail = i18n.t("clock.requestError.detail");
  } else if (snapshot.status === "checkmate" || snapshot.status === "draw") {
    tone = "terminal";
    label = i18n.t(snapshot.status === "checkmate" ? "clock.checkmate.label" : "clock.draw.label");
    value = snapshot.result || i18n.t("clock.terminal.value");
    detail = statusReasonText();
  } else if (snapshot.game_id !== null && snapshot.turn === "human") {
    tone = "human";
    label = i18n.t(snapshot.check ? "clock.human.labelCheck" : "clock.human.label");
    value = i18n.t("clock.human.value");
    detail = i18n.t("clock.human.detail", { color: colorName(snapshot.human_color) });
  } else if (snapshot.game_id !== null && snapshot.turn === "llm") {
    tone = "llm";
    label = i18n.t("clock.llm.label");
    value = i18n.t("clock.llm.value");
    detail = i18n.t("clock.llm.detail", { color: colorName(snapshot.llm_color) });
  }

  elements.clockFace.dataset.tone = tone;
  elements.clockLabel.textContent = label;
  elements.clockValue.textContent = value;
  elements.clockDetail.textContent = detail;
}

/** @description 연결 상태를 색상과 텍스트로 갱신합니다. */
function renderConnection() {
  const state = ui.connection;
  const labels = {
    connecting: i18n.t("connection.connecting"),
    connected: i18n.t("connection.connected"),
    disconnected: i18n.t("connection.disconnected"),
    error: i18n.t("connection.error"),
  };
  elements.connectionValue.textContent = labels[state];
  elements.connectionValue.dataset.state = state;
  elements.statusDot.dataset.state = state;
  elements.liveIndicator.dataset.state = state === "connected" ? "live" : "waiting";
  elements.liveIndicator.lastChild.textContent = state === "connected" ? i18n.t("live.connected") : i18n.t("live.waiting");
  elements.errorCopy.hidden = !ui.error;
  elements.errorCopy.textContent = errorText();
}

/** @description 시계·상태·수순을 한 번에 그립니다. */
function render() {
  const snapshot = ui.snapshot;
  const setupWasHidden = elements.setupLayer.hidden;
  elements.appShell.dataset.status = snapshot.status;
  elements.matchId.textContent = snapshot.game_id
    ? i18n.t("match.game", { id: snapshot.game_id.slice(0, 8) })
    : i18n.t("match.none");
  elements.boardCaption.textContent = snapshot.game_id
    ? i18n.t(snapshot.turn === "human" ? "board.caption.human" : snapshot.turn === "llm" ? "board.caption.llm" : "board.caption.terminal", { color: colorName(snapshot.human_color) })
    : i18n.t("board.chooseColor");
  elements.boardStatus.textContent = statusText();
  elements.revisionLabel.textContent = i18n.t("board.revision", { revision: snapshot.revision });
  renderClock();
  renderConnection();
  renderBoard();
  renderLastMove();
  renderMoveHistory();
  elements.setupLayer.hidden = !ui.setupOpen;
  elements.topbar.inert = ui.setupOpen;
  elements.workspace.inert = ui.setupOpen;
  elements.newGameButton.disabled = ui.requestPending;
  elements.colorButtons.forEach((button) => {
    button.disabled = ui.requestPending;
  });
  elements.setupError.hidden = !ui.error || !ui.setupOpen;
  elements.setupError.textContent = errorText();
  if (ui.setupOpen && setupWasHidden) {
    requestAnimationFrame(() => elements.colorButtons[0].focus());
  } else if (!ui.setupOpen && !setupWasHidden) {
    const returnFocus = ui.setupReturnFocus || elements.newGameButton;
    ui.setupReturnFocus = null;
    requestAnimationFrame(() => returnFocus.focus());
  }
}

/** @description 마지막 수를 읽기 쉬운 SAN과 UCI로 표시합니다. */
function renderLastMove() {
  const lastMove = ui.snapshot.last_move;
  if (!lastMove) {
    elements.lastMoveValue.textContent = i18n.t("lastMove.empty");
    elements.lastMoveMeta.textContent = i18n.t("lastMove.waiting");
    return;
  }
  elements.lastMoveValue.textContent = lastMove.san;
  elements.lastMoveMeta.textContent = i18n.t("lastMove.meta", {
    actor: i18n.t(lastMove.actor === "human" ? "actor.human" : "actor.llm"),
    uci: lastMove.uci,
  });
}

/** @description 현재 게임 수순을 번호별 두 칸 목록으로 표시합니다. */
function renderMoveHistory() {
  const history = ui.snapshot.move_history;
  elements.moveList.replaceChildren();
  elements.moveCount.textContent = i18n.t("history.count", { count: history.length });
  elements.moveCount.setAttribute("aria-label", i18n.t("history.count", { count: history.length }));
  elements.emptyHistory.hidden = history.length > 0;
  if (history.length === 0) {
    return;
  }

  for (let index = 0; index < history.length; index += 2) {
    const whiteMove = history[index];
    const blackMove = history[index + 1];
    const item = document.createElement("li");
    const number = document.createElement("span");
    const first = document.createElement("span");
    const separator = document.createElement("span");
    const second = document.createElement("span");
    number.className = "move-number";
    first.className = `move-san${whiteMove.actor === "human" ? " is-human" : ""}`;
    separator.className = "move-separator";
    second.className = `move-san${blackMove && blackMove.actor === "human" ? " is-human" : ""}`;
    number.textContent = `${Math.floor(index / 2) + 1}.`;
    first.textContent = whiteMove.san;
    separator.textContent = "·";
    second.textContent = blackMove ? blackMove.san : "—";
    item.setAttribute("aria-label", i18n.t("history.moveAria", {
      number: Math.floor(index / 2) + 1,
      first: whiteMove.san,
      second: blackMove ? i18n.t("history.movePair", { move: blackMove.san }) : "",
    }));
    item.append(number, first, separator, second);
    elements.moveList.append(item);
  }
  elements.moveList.scrollTop = elements.moveList.scrollHeight;
}




/* =================================== 체스판 조작 =================================== */


/** @description 사람 색상에 맞는 보드 칸 순서를 반환합니다. */
function orderedSquares() {
  const files = ui.snapshot.human_color === "black" ? ["h", "g", "f", "e", "d", "c", "b", "a"] : ["a", "b", "c", "d", "e", "f", "g", "h"];
  const ranks = ui.snapshot.human_color === "black" ? ["1", "2", "3", "4", "5", "6", "7", "8"] : ["8", "7", "6", "5", "4", "3", "2", "1"];
  return ranks.flatMap((rank) => files.map((file) => `${file}${rank}`));
}

/** @description 서버가 준 UCI 목록에서 출발 칸의 수를 찾습니다. */
function legalMovesFrom(square) {
  return ui.snapshot.legal_moves.filter((move) => move.from === square);
}

/** @description 현재 선택 칸과 도착 칸에 대응하는 서버 수를 찾습니다. */
function legalMovesTo(square) {
  return ui.snapshot.legal_moves.filter((move) => move.from === ui.selectedSquare && move.to === square);
}

/** @description 체스판 칸을 서버 상태와 강조 상태에 맞춰 그립니다. */
function renderBoard() {
  const snapshot = ui.snapshot;
  const focusedSquare = document.activeElement?.classList.contains("square")
    ? document.activeElement.dataset.square
    : null;
  const legalTargets = new Set(legalMovesFrom(ui.selectedSquare).map((move) => move.to));
  const lastMove = snapshot.last_move;
  const canMove = canHumanMove();
  elements.board.dataset.locked = String(snapshot.status === "active" && !canMove);
  elements.board.replaceChildren();

  orderedSquares().forEach((square, index) => {
    const button = document.createElement("button");
    const piece = snapshot.pieces[square] || "";
    const file = square[0];
    const rank = square[1];
    button.type = "button";
    button.className = `square ${(index + Math.floor(index / 8)) % 2 === 0 ? "square-light" : "square-dark"}`;
    button.dataset.square = square;
    button.setAttribute("aria-disabled", String(!canMove));
    button.setAttribute("aria-pressed", String(square === ui.selectedSquare));
    const pieceLabel = piece ? `${square}, ${pieceName(piece)}` : i18n.t("square.empty", { square });
    button.setAttribute("aria-label", legalTargets.has(square) ? `${pieceLabel}, ${i18n.t("square.legalSuffix")}` : pieceLabel);
    button.draggable = canMove && legalMovesFrom(square).length > 0;
    if (piece) {
      button.append(document.createTextNode(PIECE_GLYPHS[piece]));
    }
    if (index >= 56) {
      const fileLabel = document.createElement("span");
      fileLabel.className = "square-coordinate";
      fileLabel.textContent = file;
      fileLabel.setAttribute("aria-hidden", "true");
      button.append(fileLabel);
    }
    if (index % 8 === 0) {
      const rankLabel = document.createElement("span");
      rankLabel.className = "square-coordinate coordinate-rank";
      rankLabel.textContent = rank;
      rankLabel.setAttribute("aria-hidden", "true");
      button.append(rankLabel);
    }
    if (square === ui.selectedSquare) {
      button.classList.add("is-selected");
    }
    if (legalTargets.has(square)) {
      button.classList.add("is-legal");
    }
    if (lastMove && (square === lastMove.from || square === lastMove.to)) {
      button.classList.add("is-last-move");
    }
    if (snapshot.checked_king_square === square) {
      button.classList.add("is-checked");
    }
    button.addEventListener("click", () => handleSquareClick(square));
    button.addEventListener("dragstart", (event) => handleDragStart(event, square));
    button.addEventListener("dragend", handleDragEnd);
    button.addEventListener("dragover", handleDragOver);
    button.addEventListener("drop", (event) => handleDrop(event, square));
    elements.board.append(button);
  });
  if (focusedSquare) {
    elements.board.querySelector(`[data-square="${focusedSquare}"]`)?.focus();
  }
}

/** @description 클릭으로 칸을 선택하거나 서버 합법 수를 제출합니다. */
function handleSquareClick(square) {
  if (!canHumanMove()) {
    return;
  }
  if (!ui.selectedSquare) {
    if (legalMovesFrom(square).length > 0) {
      ui.selectedSquare = square;
      renderBoard();
    }
    return;
  }
  if (square === ui.selectedSquare) {
    ui.selectedSquare = null;
    renderBoard();
    return;
  }
  const candidates = legalMovesTo(square);
  if (candidates.length === 0) {
    ui.selectedSquare = legalMovesFrom(square).length > 0 ? square : null;
    renderBoard();
    return;
  }
  chooseMove(candidates);
}

/** @description 끌어놓기 시작 칸을 기억합니다. */
function handleDragStart(event, square) {
  if (!canHumanMove() || legalMovesFrom(square).length === 0) {
    event.preventDefault();
    return;
  }
  ui.selectedSquare = square;
  event.dataTransfer.effectAllowed = "move";
  event.dataTransfer.setData("text/plain", square);
}

/** @description 끌어놓기가 끝난 뒤 취소된 선택을 정리합니다. */
function handleDragEnd() {
  if (!ui.requestPending && ui.promotionMoves.length === 0) {
    ui.selectedSquare = null;
    renderBoard();
  }
}

/** @description 합법 도착 칸에만 끌어놓기를 허용합니다. */
function handleDragOver(event) {
  if (canHumanMove() && ui.selectedSquare && legalMovesTo(event.currentTarget.dataset.square).length > 0) {
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
  }
}

/** @description 끌어놓기 수를 서버가 준 후보에서 선택합니다. */
function handleDrop(event, square) {
  event.preventDefault();
  if (!canHumanMove()) {
    return;
  }
  const candidates = legalMovesTo(square);
  if (candidates.length > 0) {
    chooseMove(candidates);
  }
}

/** @description 승진이 필요한 경우 선택창을 열고 아니면 UCI를 전송합니다. */
function chooseMove(candidates) {
  if (candidates.length === 1) {
    submitHumanMove(candidates[0].uci);
    return;
  }
  ui.promotionMoves = candidates;
  elements.promotionOptions.replaceChildren();
  candidates.forEach((move) => {
    const promotion = String(move.promotion).toLowerCase();
    const option = document.createElement("button");
    const glyph = document.createElement("span");
    const name = document.createElement("small");
    option.className = "promotion-option";
    option.type = "button";
    option.dataset.uci = move.uci;
    option.setAttribute("aria-label", i18n.t("promotion.action", {
      piece: promotionName(promotion),
      uci: move.uci,
    }));
    glyph.className = "promotion-glyph";
    glyph.textContent = PIECE_GLYPHS[ui.snapshot.human_color === "white" ? promotion.toUpperCase() : promotion];
    name.textContent = promotionName(promotion);
    option.append(glyph, name);
    option.addEventListener("click", () => {
      elements.promotionDialog.close();
      submitHumanMove(move.uci);
    });
    elements.promotionOptions.append(option);
  });
  elements.promotionDialog.showModal();
}

/** @description 사람의 정확한 UCI 수를 서버에 제출합니다. */
async function submitHumanMove(uci) {
  if (!canHumanMove()) {
    return;
  }
  ui.requestPending = true;
  ui.selectedSquare = null;
  ui.error = null;
  render();
  try {
    const snapshot = await requestJson("/api/human/moves", {
      method: "POST",
      body: JSON.stringify({ move: uci }),
    });
    applySnapshot(snapshot);
    ui.connection = "connected";
  } catch (error) {
    ui.error = localizedErrorState(error, "error.move");
  } finally {
    ui.requestPending = false;
    render();
  }
}




/* =================================== 게임 시작과 이벤트 =================================== */


/** @description 새 게임 색상 선택 화면을 엽니다. */
function openNewGame() {
  const snapshot = ui.snapshot;
  if (snapshot.status === "active" && snapshot.move_history.length > 0) {
    const confirmed = window.confirm(i18n.t("confirm.newGame"));
    if (!confirmed) {
      return;
    }
  }
  ui.setupReturnFocus = elements.newGameButton;
  ui.setupOpen = true;
  ui.error = null;
  ui.selectedSquare = null;
  render();
}

/** @description 선택한 사람 색상으로 메모리 게임을 시작합니다. */
async function startGame(color) {
  ui.requestPending = true;
  ui.error = null;
  render();
  try {
    const snapshot = await requestJson("/api/games", {
      method: "POST",
      body: JSON.stringify({ human_color: color }),
    });
    applySnapshot(snapshot);
    ui.setupOpen = false;
    ui.connection = "connected";
  } catch (error) {
    ui.connection = "error";
    ui.error = localizedErrorState(error, "error.start");
  } finally {
    ui.requestPending = false;
    render();
  }
}

/** @description 서버 SSE 연결을 시작하고 브라우저 기본 재연결을 사용합니다. */
function connectEvents() {
  const stream = new EventSource("/api/events");
  stream.addEventListener("open", () => {
    ui.connection = "connected";
    ui.error = null;
    render();
  });
  stream.addEventListener("message", handleServerEvent);
  stream.addEventListener("error", () => {
    ui.connection = "disconnected";
    render();
  });
}

/** @description 브라우저 이벤트를 연결합니다. */
function bindEvents() {
  elements.newGameButton.addEventListener("click", openNewGame);
  elements.colorButtons.forEach((button) => {
    button.addEventListener("click", () => startGame(button.dataset.color));
  });
  elements.localeSelects.forEach((select) => {
    select.addEventListener("change", () => i18n.setLocale(select.value));
  });
  elements.promotionDialog.addEventListener("close", () => {
    ui.promotionMoves = [];
    ui.selectedSquare = null;
    renderBoard();
  });
  elements.promotionCancel.addEventListener("click", () => {
    ui.promotionMoves = [];
    ui.selectedSquare = null;
  });
}

i18n.subscribe(() => {
  applyStaticCopy();
  render();
});

applyStaticCopy();
bindEvents();
render();
loadState();
connectEvents();
