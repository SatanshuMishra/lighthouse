export function setupList(doc) {
  const input = doc.getElementById("pantry-item");
  const addButton = doc.getElementById("pantry-add");
  const items = doc.getElementById("pantry-items");
  const count = doc.getElementById("pantry-count");

  function addItem() {
    const name = input.value.trim();
    if (!name) {
      return;
    }
    const entry = doc.createElement("li");
    entry.textContent = name;
    items.appendChild(entry);
    const total = items.children.length;
    count.textContent = total + (total === 1 ? " item" : " items");
    input.value = "";
    input.focus();
  }

  addButton.addEventListener("click", addItem);
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      addItem();
    }
  });
}
