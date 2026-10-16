const choice = document.getElementById("tea-choice");
const startButton = document.getElementById("steep-start");
const clock = document.getElementById("steep-clock");

let deadline = 0;
let ticker = null;

function clockText(seconds) {
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return minutes + ":" + String(rest).padStart(2, "0");
}

function chosenSeconds() {
  return Number(choice.value);
}

function stop() {
  clearInterval(ticker);
  ticker = null;
  startButton.textContent = "Start";
}

function showChoice() {
  if (ticker === null) {
    clock.textContent = clockText(chosenSeconds());
  }
}

function tick() {
  const left = Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
  if (left === 0) {
    stop();
    clock.textContent = "Ready";
    return;
  }
  clock.textContent = clockText(left);
}

startButton.addEventListener("click", () => {
  if (ticker !== null) {
    stop();
    showChoice();
    return;
  }
  deadline = Date.now() + chosenSeconds() * 1000;
  startButton.textContent = "Stop";
  clock.textContent = clockText(chosenSeconds());
  ticker = setInterval(tick, 250);
});

choice.addEventListener("change", showChoice);
