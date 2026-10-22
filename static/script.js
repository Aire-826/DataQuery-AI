
const fileInput = document.getElementById("csvFile");
const fileLabel = document.getElementById("fileLabel");
const statusMessage = document.getElementById("uploadStatus");
const tableHead = document.getElementById("tableHead");
const tableBody = document.getElementById("tableBody");

const chatForm = document.getElementById("chatForm");
const questionInput = document.getElementById("question");
const sendButton = document.getElementById("sendButton");
const chatMessages = document.getElementById("chatMessages");
const chatSubtitle = document.getElementById("chatSubtitle");

let currentFile = null;

fileInput.addEventListener("change", async () => {
    const file = fileInput.files[0];
    if (!file) return;

    if (!file.name.toLowerCase().endsWith(".csv")) {
        statusMessage.textContent = "Please select a CSV file.";
        fileInput.value = "";
        return;
    }

    if (file.size > 5 * 1024 * 1024) {
        statusMessage.textContent = "Maximum file size is 5 MB.";
        fileInput.value = "";
        return;
    }

    fileLabel.textContent = file.name;
    statusMessage.textContent = "Uploading and analyzing your CSV...";

    currentFile = null;
    questionInput.disabled = true;
    sendButton.disabled = true;

    const formData = new FormData();
    formData.append("file", file);

    try {
        const response = await fetch("/api/upload", {
            method: "POST",
            body: formData
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.detail || "Upload failed.");
        }

        currentFile = file;

        document.getElementById("rowCount").textContent =
            result.rows.toLocaleString();

        document.getElementById("columnCount").textContent =
            result.columns_count;

        document.getElementById("numericCount").textContent =
            Object.values(result.data_types).filter(type =>
                ["int64", "int32", "float64", "float32"].includes(type)
            ).length;

        document.getElementById("previewDescription").textContent =
            `${result.filename} · Showing ${result.preview.length} rows`;

        renderTable(result.columns, result.preview);

        statusMessage.textContent =
            "Dataset uploaded and analyzed successfully.";

        chatSubtitle.textContent = `Ready to explore ${result.filename}`;
        questionInput.disabled = false;
        sendButton.disabled = false;

        addMessage(
            "assistant",
            `I've loaded ${result.rows} rows and ${result.columns_count} columns. Ask me a question about your data.`
        );
    } catch (error) {
        statusMessage.textContent = error.message;
        currentFile = null;
        chatSubtitle.textContent = "Upload a valid CSV to begin";
    }
});

function renderTable(columns, rows) {
    tableHead.replaceChildren();
    tableBody.replaceChildren();

    const headerRow = document.createElement("tr");

    columns.forEach(column => {
        const th = document.createElement("th");
        th.textContent = column;
        headerRow.appendChild(th);
    });

    tableHead.appendChild(headerRow);

    rows.forEach(row => {
        const tr = document.createElement("tr");

        columns.forEach(column => {
            const td = document.createElement("td");
            const value = row[column];

            td.textContent =
                value === null || value === undefined ? "—" : String(value);

            tr.appendChild(td);
        });

        tableBody.appendChild(tr);
    });
}

function addMessage(role, text) {
    const message = document.createElement("div");
    message.className =
        `chat-message ${role === "user" ? "user-message" : "assistant-message"}`;

    const paragraph = document.createElement("p");
    paragraph.textContent = text;

    if (role === "assistant") {
        const icon = document.createElement("div");
        icon.className = "bot-icon small";
        icon.textContent = "✦";
        message.appendChild(icon);
    }

    message.appendChild(paragraph);
    chatMessages.appendChild(message);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

async function askQuestion(question) {
    if (!currentFile || sendButton.disabled) return;

    addMessage("user", question);

    const formData = new FormData();
    formData.append("file", currentFile);
    formData.append("question", question);

    sendButton.disabled = true;
    questionInput.disabled = true;
    statusMessage.textContent = "Analyzing your question...";

    try {
        const response = await fetch("/api/ask", {
            method: "POST",
            body: formData
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.detail || "Question failed.");
        }

        addMessage("assistant", result.answer);
        statusMessage.textContent = "Analysis complete.";
    } catch (error) {
        addMessage("assistant", `Sorry, I couldn't answer that: ${error.message}`);
        statusMessage.textContent = "Question could not be processed.";
    } finally {
        sendButton.disabled = false;
        questionInput.disabled = false;
        questionInput.focus();
    }
}

chatForm.addEventListener("submit", event => {
    event.preventDefault();

    const question = questionInput.value.trim();
    if (!question || !currentFile) {
        if (!currentFile) {
            statusMessage.textContent = "Upload a CSV file first.";
        }
        return;
    }

    questionInput.value = "";
    askQuestion(question);
});

document.querySelectorAll(".suggestion").forEach(button => {
    button.addEventListener("click", () => {
        if (!currentFile) {
            statusMessage.textContent = "Upload a CSV file first.";
            return;
        }

        askQuestion(button.textContent.trim());
    });
});
