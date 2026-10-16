const PICKS = ["Milk", "Eggs", "Bread", "Rice"];

export function setupQuickPicks(doc) {
  const input = doc.getElementById("pantry-item");
  const row = doc.createElement("div");
  row.id = "quick-picks";
  row.setAttribute("aria-label", "Quick picks");
  for (const name of PICKS) {
    const chip = doc.createElement("button");
    chip.type = "button";
    chip.className = "quick-pick";
    chip.textContent = name;
    chip.addEventListener("click", () => {
      input.value = name;
      const addButton = doc.getElementById("pantry-submit");
      if (addButton) {
        addButton.click();
      }
    });
    row.appendChild(chip);
  }
  doc.getElementById("pantry-form").insertAdjacentElement("afterend", row);
}
