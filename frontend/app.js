const API_BASE = "http://127.0.0.1:8000";
const WS_URL = "ws://127.0.0.1:8000/ws";

const PRODUCTS = [
    "everest",
    "mayo",
    "shampoo",
    "vaseline",
    "chocopie"
];

let socket = null;
let reconnectTimer = null;
let currentVideo = null;


/* -------------------------------------------------------
   DOM
------------------------------------------------------- */

const connectionStatus =
    document.getElementById("connectionStatus");

const cartItems =
    document.getElementById("cartItems");

const totalItems =
    document.getElementById("totalItems");

const total =
    document.getElementById("total");

const lastEvent =
    document.getElementById("lastEvent");

const lastTrack =
    document.getElementById("lastTrack");

const videoSelector =
    document.getElementById("videoSelector");

const videoFeed =
    document.getElementById("videoFeed");

const videoPlaceholder =
    document.getElementById("videoPlaceholder");

const cvStatus =
    document.getElementById("cvStatus");

const startVideoButton =
    document.getElementById("startVideoButton");

const stopVideoButton =
    document.getElementById("stopVideoButton");

const resetCartButton =
    document.getElementById("resetCartButton");


/* -------------------------------------------------------
   CART
------------------------------------------------------- */

function renderCart(items) {

    cartItems.innerHTML = "";

    for (const product of PRODUCTS) {

        const quantity = items?.[product] ?? 0;

        const row = document.createElement("div");

        row.className = "cart-item";

        row.innerHTML = `
            <span class="product-name">
                ${formatProductName(product)}
            </span>

            <span class="product-quantity">
                × ${quantity}
            </span>
        `;

        cartItems.appendChild(row);
    }
}


function formatProductName(product) {

    return product.charAt(0).toUpperCase()
        + product.slice(1);
}


function renderEvent(event, trackId) {

    if (!event) {
        lastEvent.textContent = "Waiting for activity";
        lastTrack.textContent = "Track ID: —";
        return;
    }

    const product =
        event.product
            ? formatProductName(event.product)
            : "";

    lastEvent.textContent =
        `${event.event} ${product}`;

    lastTrack.textContent =
        `Track ID: ${event.track_id ?? "—"}`;
}


function handleCartUpdate(data) {

    if (!data) {
        return;
    }

    if (data.cart) {
        renderCart(data.cart);
    }

    totalItems.textContent =
        data.total_items ?? 0;

    total.textContent =
        data.total === null || data.total === undefined
            ? "₹—"
            : `₹${data.total}`;

    renderEvent(
        data.last_event,
        data.last_event?.track_id
    );
}


/* -------------------------------------------------------
   WEBSOCKET
------------------------------------------------------- */

function setConnected() {

    connectionStatus.classList.remove(
        "disconnected"
    );

    connectionStatus.classList.add(
        "connected"
    );

    connectionStatus.innerHTML = `
        <span class="status-dot"></span>
        Connected
    `;
}


function setDisconnected() {

    connectionStatus.classList.remove(
        "connected"
    );

    connectionStatus.classList.add(
        "disconnected"
    );

    connectionStatus.innerHTML = `
        <span class="status-dot"></span>
        Disconnected
    `;
}


function connectWebSocket() {

    if (
        socket &&
        (
            socket.readyState === WebSocket.OPEN ||
            socket.readyState === WebSocket.CONNECTING
        )
    ) {
        return;
    }

    socket = new WebSocket(WS_URL);

    socket.onopen = () => {

        setConnected();

        console.log("[WS] Connected");

        clearTimeout(reconnectTimer);
    };


    socket.onmessage = (message) => {

        try {

            const data =
                JSON.parse(message.data);

            console.log("[WS] Received:", data);

            handleCartUpdate(data);

        } catch (error) {

            console.error(
                "[WS] Invalid message:",
                error
            );
        }
    };


    socket.onclose = () => {

        setDisconnected();

        console.log("[WS] Disconnected");

        reconnectTimer =
            setTimeout(
                connectWebSocket,
                2000
            );
    };


    socket.onerror = (error) => {

        console.error(
            "[WS] Error:",
            error
        );
    };
}


/* -------------------------------------------------------
   VIDEO
------------------------------------------------------- */

async function loadVideos() {

    try {

        const response =
            await fetch(
                `${API_BASE}/api/videos`
            );

        const data =
            await response.json();

        videoSelector.innerHTML = `
            <option value="">
                Select demonstration video
            </option>
        `;

        for (const filename of data.demo || []) {

            const option =
                document.createElement("option");

            option.value = filename;
            option.textContent =
                filename;

            videoSelector.appendChild(option);
        }

    } catch (error) {

        console.error(
            "Failed to load videos:",
            error
        );
    }
}


function startVideo() {

    const filename =
        videoSelector.value;

    if (!filename) {

        alert(
            "Select a demonstration video first."
        );

        return;
    }

    currentVideo = filename;

    const encodedFilename =
        encodeURIComponent(filename);

    /*
       This endpoint will be implemented
       in the CV backend in the next step.
    */

    videoFeed.src =
        `${API_BASE}/video_feed?video=${encodedFilename}`;

    videoFeed.classList.remove("hidden");

    videoPlaceholder.classList.add("hidden");

    cvStatus.textContent =
        "CV ENGINE RUNNING";
}


function stopVideo() {

    videoFeed.src = "";

    videoFeed.classList.add("hidden");

    videoPlaceholder.classList.remove("hidden");

    cvStatus.textContent =
        "CV ENGINE OFF";

    currentVideo = null;
}


/* -------------------------------------------------------
   BUTTONS
------------------------------------------------------- */

startVideoButton.addEventListener(
    "click",
    startVideo
);

stopVideoButton.addEventListener(
    "click",
    stopVideo
);


resetCartButton.addEventListener(
    "click",
    async () => {

        try {

            await fetch(
                `${API_BASE}/api/cart/reset`,
                {
                    method: "POST"
                }
            );

        } catch (error) {

            console.error(
                "Failed to reset cart:",
                error
            );
        }
    }
);


/* -------------------------------------------------------
   INITIALIZATION
------------------------------------------------------- */

renderCart({
    everest: 0,
    mayo: 0,
    shampoo: 0,
    vaseline: 0,
    chocopie: 0
});

connectWebSocket();

loadVideos();
