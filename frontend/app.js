"use strict";

const state = {
  studentId: null,
  studentName: "",
  age: null,
  topic: null,
  lastAudioUrl: null,
};

const el = {
  setupScreen: document.getElementById("setup-screen"),
  lessonScreen: document.getElementById("lesson-screen"),
  nameInput: document.getElementById("name-input"),
  ageRow: document.getElementById("age-row"),
  topicRow: document.getElementById("topic-row"),
  startBtn: document.getElementById("start-btn"),
  setupError: document.getElementById("setup-error"),
  chatLog: document.getElementById("chat-log"),
  gameArea: document.getElementById("game-area"),
  replyForm: document.getElementById("reply-form"),
  replyInput: document.getElementById("reply-input"),
  replayBtn: document.getElementById("replay-audio-btn"),
  micBtn: document.getElementById("mic-btn"),
  voiceStatus: document.getElementById("voice-status"),
  loading: document.getElementById("loading-indicator"),
  agentAudio: document.getElementById("agent-audio"),
};

function setLoading(isLoading) {
  el.loading.hidden = !isLoading;
}

function updateStartButtonState() {
  const nameOk = el.nameInput.value.trim().length > 0;
  el.startBtn.disabled = !(nameOk && state.age && state.topic);
}

el.nameInput.addEventListener("input", updateStartButtonState);

el.ageRow.addEventListener("click", (event) => {
  const btn = event.target.closest(".age-btn");
  if (!btn) return;
  [...el.ageRow.children].forEach((b) => b.classList.remove("selected"));
  btn.classList.add("selected");
  state.age = Number(btn.dataset.age);
  updateStartButtonState();
});

el.topicRow.addEventListener("click", (event) => {
  const btn = event.target.closest(".topic-btn");
  if (!btn) return;
  [...el.topicRow.children].forEach((b) => b.classList.remove("selected"));
  btn.classList.add("selected");
  state.topic = btn.dataset.topic;
  updateStartButtonState();
});

async function apiPost(path, body) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail || `Сервер қатесі: ${response.status}`);
  }
  return response.json();
}

function audioUrlFromPath(audioPath) {
  if (!audioPath) return null;
  const filename = audioPath.split(/[\\/]/).pop();
  return `/audio/${encodeURIComponent(filename)}`;
}

function playAudio(url) {
  if (!url) return;
  state.lastAudioUrl = url;
  el.agentAudio.src = url;
  el.agentAudio.play().catch(() => {
    // Автовоспроизведение может быть заблокировано браузером до первого клика — это нормально.
  });
}

function appendMessage(text, sender) {
  if (!text) return;
  const bubble = document.createElement("div");
  bubble.className = `msg ${sender}`;
  bubble.textContent = text;
  el.chatLog.appendChild(bubble);
  el.chatLog.scrollTop = el.chatLog.scrollHeight;
}

function clearGameArea() {
  el.gameArea.hidden = true;
  el.gameArea.innerHTML = "";
}

function renderGameChallenge(challenge) {
  clearGameArea();
  if (!challenge || challenge.error) return;

  const instruction = document.createElement("div");
  instruction.className = "game-instruction";
  instruction.textContent = challenge.instruction_kazakh || "Ойнайық!";
  el.gameArea.appendChild(instruction);

  const optionsWrap = document.createElement("div");
  optionsWrap.className = "game-options";

  const options = challenge.options || [];
  options.forEach((option) => {
    const isObject = typeof option === "object" && option !== null;
    const word = isObject ? option.word : option;
    const image = isObject ? option.image : "🔤";

    const optionBtn = document.createElement("button");
    optionBtn.type = "button";
    optionBtn.className = "game-option-btn";
    optionBtn.innerHTML = `<span>${image}</span><span class="game-option-word">${word}</span>`;
    optionBtn.addEventListener("click", () => {
      [...optionsWrap.children].forEach((b) => (b.disabled = true));
      const isCorrect = word === challenge.correct_answer;
      optionBtn.classList.add(isCorrect ? "correct" : "incorrect");
      sendMessage(word);
    });
    optionsWrap.appendChild(optionBtn);
  });

  el.gameArea.appendChild(optionsWrap);
  el.gameArea.hidden = false;
}

function handleAgentResult(result) {
  appendMessage(result.reply_text, "agent");

  const audioUrl = audioUrlFromPath(result.audio_path);
  playAudio(audioUrl);

  const gameCall = (result.tool_calls || [])
    .slice()
    .reverse()
    .find((call) => call.name === "generate_game_challenge");

  if (gameCall) {
    renderGameChallenge(gameCall.result);
  } else {
    clearGameArea();
  }
}

async function startLesson() {
  el.setupError.hidden = true;
  setLoading(true);
  try {
    const student = await apiPost("/students", {
      name: state.studentName,
      age: state.age,
      preferred_topic: state.topic,
    });
    state.studentId = student.id;

    el.setupScreen.hidden = true;
    el.lessonScreen.hidden = false;

    const result = await apiPost("/lessons/start", {
      student_id: state.studentId,
      topic: state.topic,
    });
    handleAgentResult(result);
  } catch (err) {
    el.setupError.textContent = err.message || "Қате шықты, қайталап көр.";
    el.setupError.hidden = false;
    el.setupScreen.hidden = false;
    el.lessonScreen.hidden = true;
  } finally {
    setLoading(false);
  }
}

async function sendMessage(text) {
  const trimmed = text.trim();
  if (!trimmed || !state.studentId) return;

  appendMessage(trimmed, "student");
  clearGameArea();
  setLoading(true);
  try {
    const result = await apiPost("/chat", {
      student_id: state.studentId,
      message: trimmed,
    });
    handleAgentResult(result);
  } catch (err) {
    appendMessage("Кешір, қате болды. Тағы көрейік! 🙈", "agent");
  } finally {
    setLoading(false);
  }
}

el.startBtn.addEventListener("click", () => {
  state.studentName = el.nameInput.value.trim();
  startLesson();
});

el.replyForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const text = el.replyInput.value;
  el.replyInput.value = "";
  sendMessage(text);
});

el.replayBtn.addEventListener("click", () => {
  if (state.lastAudioUrl) {
    el.agentAudio.currentTime = 0;
    el.agentAudio.play().catch(() => {});
  }
});

// ---------------------------------------------------------------------------
// Голосовой ввод (Web Speech API) — необязательное улучшение поверх текста.
// Казахский язык официально не поддерживается большинством браузеров, поэтому
// это best-effort: при отсутствии поддержки или ошибке распознавания кнопка
// просто скрыта/молча откатывается, а ввод текстом остаётся основным способом.
// ---------------------------------------------------------------------------
const SpeechRecognitionImpl = window.SpeechRecognition || window.webkitSpeechRecognition;

if (SpeechRecognitionImpl) {
  const recognition = new SpeechRecognitionImpl();
  recognition.lang = "kk-KZ";
  recognition.continuous = false;
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;

  let isListening = false;

  const stopListeningUi = () => {
    isListening = false;
    el.micBtn.classList.remove("listening");
    el.voiceStatus.hidden = true;
  };

  recognition.addEventListener("result", (event) => {
    const transcript = event.results[0][0].transcript.trim();
    if (transcript) {
      sendMessage(transcript);
    }
  });

  recognition.addEventListener("error", (event) => {
    if (event.error === "no-speech") {
      appendMessage("Ештеңе естімедім, тағы айтып көр немесе жаз. 🙉", "agent");
    }
  });

  recognition.addEventListener("end", stopListeningUi);

  el.micBtn.hidden = false;
  el.micBtn.addEventListener("click", () => {
    if (isListening) {
      recognition.stop();
      return;
    }
    isListening = true;
    el.micBtn.classList.add("listening");
    el.voiceStatus.hidden = false;
    try {
      recognition.start();
    } catch {
      stopListeningUi();
    }
  });
}
