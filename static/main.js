"use strict";

const chat = document.getElementById("messages");
const form = document.getElementById("askForm");
const input = document.getElementById("question");
const send = document.getElementById("send");
const typing = document.getElementById("typing");

const expertConversations =
    document.getElementById("expertConversations");

const expertThread =
    document.getElementById("expertThread");

const expertMessages =
    document.getElementById("expertMessages");

const expertTicketNumber =
    document.getElementById("expertTicketNumber");

const expertTicketStatus =
    document.getElementById("expertTicketStatus");

const refreshExpert =
    document.getElementById("refreshExpert");

const replyForm =
    document.getElementById("customerReplyForm");

const replyText =
    document.getElementById("customerReplyText");

const replySend =
    document.getElementById("customerReplySend");

const STORAGE_KEY = "destek_talepler_v1";

let selectedTicket = null;
let loadingMessages = false;
let lastMessagesSignature = "";


const statuses = {
    yeni: "Yanıt bekleniyor",
    inceleniyor: "İnceleniyor",
    cozuldu: "Çözüldü"
};


function bubble(text, role, secondary = "") {

    const row = document.createElement("div");

    row.className = "bubble-row " + role;

    const element = document.createElement("div");

    element.className = "bubble";

    element.textContent = text;

    row.append(element);

    if (secondary) {

        const hint = document.createElement("div");

        hint.className = "bubble-hint";

        hint.textContent = secondary;

        element.append(hint);
    }

    chat.append(row);

    chat.scrollTop = chat.scrollHeight;
}


function getTickets() {

    try {

        const data = JSON.parse(
            localStorage.getItem(STORAGE_KEY) || "[]"
        );

        if (!Array.isArray(data)) return [];

        return data.filter(ticket =>
            ticket &&
            typeof ticket.number === "string" &&
            typeof ticket.key === "string"
        );

    } catch {

        return [];
    }
}


function storeTickets(tickets) {

    try {

        localStorage.setItem(
            STORAGE_KEY,
            JSON.stringify(tickets.slice(0, 60))
        );

    } catch (error) {

        console.warn("Talep kaydedilemedi.", error);
    }
}


function saveTicket(ticket) {

    const tickets = getTickets();

    const index = tickets.findIndex(
        item => item.number === ticket.number
    );

    if (index >= 0) {

        tickets[index] = ticket;

    } else {

        tickets.unshift(ticket);
    }

    storeTickets(tickets);

    renderExpertConversations();
}


function updateSavedTicket(number, changes) {

    const tickets = getTickets();

    const index = tickets.findIndex(
        item => item.number === number
    );

    if (index < 0) return;

    tickets[index] = {
        ...tickets[index],
        ...changes
    };

    storeTickets(tickets);
}


function createStatusBadge(status) {

    const badge = document.createElement("span");

    badge.className = "support-status";

    if (status === "cozuldu") {

        badge.classList.add("answered");

    } else if (status === "inceleniyor") {

        badge.classList.add("reviewing");

    } else {

        badge.classList.add("pending");
    }

    badge.textContent =
        statuses[status] || "Yanıt bekleniyor";

    return badge;
}


function renderExpertConversations() {

    expertConversations.replaceChildren();

    const tickets = getTickets();

    if (!tickets.length) {

        const empty = document.createElement("div");

        empty.className = "expert-empty";

        empty.textContent =
            "Henüz bir destek görüşmeniz bulunmuyor.";

        expertConversations.append(empty);

        expertThread.classList.add("hidden");

        return;
    }

    tickets.forEach(ticket => {

        const button = document.createElement("button");

        button.type = "button";

        button.className = "support-conversation";

        const icon = document.createElement("div");

        icon.className = "support-conversation-icon";

        icon.textContent = "💬";

        const content = document.createElement("div");

        content.className = "support-conversation-content";

        const title = document.createElement("strong");

        title.textContent =
            ticket.question || "Destek görüşmesi";

        const subtitle = document.createElement("small");

        subtitle.textContent =
            "Görüşmeyi aç";

        content.append(title, subtitle);

        const right = document.createElement("div");

        right.className = "support-conversation-right";

        const badge = createStatusBadge(ticket.status);

        const arrow = document.createElement("span");

        arrow.className = "support-arrow";

        arrow.textContent = "›";

        right.append(badge, arrow);

        button.append(icon, content, right);

        button.addEventListener("click", () => {

            openExpertConversation(ticket);

        });

        expertConversations.append(button);
    });
}


function formatDate(value) {

    const date = new Date(value);

    if (Number.isNaN(date.getTime())) return "";

    return date.toLocaleString("tr-TR");
}


function renderConversationMessages(messages) {

    expertMessages.replaceChildren();

    messages.forEach(item => {

        const row = document.createElement("div");

        row.className =
            "expert-message-row " +
            (item.sender === "customer" ? "customer" : "expert");

        const bubble = document.createElement("div");

        bubble.className = "expert-message";

        const sender = document.createElement("strong");

        sender.textContent =
            item.sender === "customer"
                ? "Siz"
                : "Uzman";

        const content = document.createElement("div");

        content.textContent = item.message;

        const date = document.createElement("small");

        date.style.display = "block";
        date.style.marginTop = "7px";
        date.style.opacity = ".65";

        date.textContent = formatDate(item.created_at);

        bubble.append(sender, content, date);

        row.append(bubble);

        expertMessages.append(row);

    });

    expertMessages.scrollTop =
        expertMessages.scrollHeight;
}


async function openExpertConversation(ticket) {

    selectedTicket = ticket;

    lastMessagesSignature = "";

    expertThread.classList.remove("hidden");

    expertTicketNumber.textContent =
        "Destek görüşmesi";

    expertTicketStatus.textContent =
        "Kontrol ediliyor...";

    expertMessages.replaceChildren();

    await checkExpertReply();

    expertThread.scrollIntoView({
        behavior: "smooth",
        block: "nearest"
    });
}


async function checkExpertReply() {

    if (!selectedTicket || loadingMessages) return;

    const ticket = selectedTicket;

    loadingMessages = true;

    try {

        const response = await fetch(
            "/api/talep-durumu",
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    number: ticket.number,
                    key: ticket.key
                })
            }
        );

        if (!response.ok) {

            throw new Error(
                "Görüşme bilgileri alınamadı."
            );
        }

        const data = await response.json();

        if (selectedTicket !== ticket) return;

        ticket.question = data.question;
        ticket.status = data.status;

        updateSavedTicket(ticket.number, {
            question: data.question,
            status: data.status
        });

        expertTicketStatus.textContent =
            statuses[data.status] || data.status;

        expertTicketStatus.className =
            "support-status " +
            (
                data.status === "cozuldu"
                    ? "answered"
                    : data.status === "inceleniyor"
                    ? "reviewing"
                    : "pending"
            );

        const signature = JSON.stringify(data.messages);

        if (signature !== lastMessagesSignature) {

            renderConversationMessages(data.messages);

            lastMessagesSignature = signature;
        }

        renderExpertConversations();

    } catch (error) {

        if (selectedTicket === ticket) {

            expertTicketStatus.textContent =
                "Bağlantı hatası";
        }

    } finally {

        loadingMessages = false;
    }
}


refreshExpert.addEventListener("click", checkExpertReply);


replyForm.addEventListener("submit", async event => {

    event.preventDefault();

    if (!selectedTicket || replySend.disabled) return;

    const message = replyText.value.trim();

    if (!message) return;

    const ticket = selectedTicket;

    replySend.disabled = true;

    try {

        const response = await fetch(
            "/api/talep-mesaj",
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    number: ticket.number,
                    key: ticket.key,
                    message: message
                })
            }
        );

        if (!response.ok) {

            const data = await response.json().catch(() => ({}));

            throw new Error(
                data.detail || "Mesaj gönderilemedi."
            );
        }

        replyText.value = "";

        ticket.status = "yeni";

        lastMessagesSignature = "";

        await checkExpertReply();

    } catch (error) {

        alert(error.message);

    } finally {

        replySend.disabled = false;
    }
});


form.addEventListener("submit", async event => {

    event.preventDefault();

    if (send.disabled) return;

    const message = input.value.trim();

    if (message.length < 2) return;

    input.value = "";

    bubble(message, "human");

    send.disabled = true;

    typing.classList.remove("hidden");

    try {

        const response = await fetch(
            "/api/sor",
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    message: message
                })
            }
        );

        const data = await response.json();

        if (!response.ok) {

            throw new Error(
                data.detail || "İstek başarısız."
            );
        }

        if (data.type === "ticket") {

            bubble(
                "Sorunuz uzman ekibimize iletildi. " +
                "Destek Mesajlarım bölümünden görüşmeye devam edebilirsiniz.",
                "bot",
                "Uzman desteği"
            );

            const ticket = {
                number: data.ticket_number,
                key: data.ticket_key,
                question: message,
                status: "yeni"
            };

            saveTicket(ticket);

            await openExpertConversation(ticket);

        } else {

            bubble(
                data.text,
                "bot",
                "Yapay zekâ yanıtı"
            );
        }

    } catch (error) {

        bubble(
            "Bir hata oluştu: " + error.message,
            "bot"
        );

    } finally {

        typing.classList.add("hidden");

        send.disabled = false;

        input.focus();
    }
});


document.querySelectorAll("[data-question]").forEach(button => {

    button.addEventListener("click", () => {

        input.value = button.dataset.question;

        input.focus();
    });
});


async function syncOldTickets() {

    const tickets = getTickets();

    // Limit initial synchronization to avoid API rate limits.
    for (const ticket of tickets.slice(0, 8)) {

        try {

            const response = await fetch(
                "/api/talep-durumu",
                {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({
                        number: ticket.number,
                        key: ticket.key
                    })
                }
            );

            if (!response.ok) continue;

            const data = await response.json();

            updateSavedTicket(ticket.number, {
                question: data.question,
                status: data.status
            });

        } catch {

            // Do not interrupt other tickets.
        }
    }

    renderExpertConversations();
}


// Poll only the currently selected conversation.

setInterval(() => {

    if (!document.hidden && selectedTicket) {

        checkExpertReply();
    }

}, 12000);


document.addEventListener("visibilitychange", () => {

    if (!document.hidden && selectedTicket) {

        checkExpertReply();
    }
});


renderExpertConversations();

syncOldTickets();