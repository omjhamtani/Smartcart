import asyncio
from pathlib import Path
from typing import Optional

from fastapi import (
    FastAPI,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    FileResponse,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from cart_manager import CartManager
from config import (
    CART_FILE,
    CONTROLLED_VIDEOS_DIR,
    DEMO_VIDEOS_DIR,
    PRODUCTS,
)
from cv_engine import generate_mjpeg


# =========================================================
# APPLICATION
# =========================================================

app = FastAPI(
    title="SmartCart Backend",
    version="1.0.0",
)


# =========================================================
# PATHS
# =========================================================

BASE_DIR = (
    Path(__file__).resolve().parent.parent
)

FRONTEND_DIR = (
    BASE_DIR / "frontend"
)


# =========================================================
# STATIC FRONTEND
# =========================================================

app.mount(
    "/static",
    StaticFiles(
        directory=FRONTEND_DIR
    ),
    name="static",
)


# =========================================================
# CORS
# =========================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================================================
# CART
# =========================================================

cart_manager = CartManager(
    CART_FILE
)


# =========================================================
# WEBSOCKET MANAGER
# =========================================================

class ConnectionManager:

    def __init__(self):

        self.active_connections: list[
            WebSocket
        ] = []

    async def connect(
        self,
        websocket: WebSocket,
    ):

        await websocket.accept()

        self.active_connections.append(
            websocket
        )

        print(
            "[WS] Client connected "
            f"({len(self.active_connections)} active)"
        )

    def disconnect(
        self,
        websocket: WebSocket,
    ):

        if websocket in self.active_connections:

            self.active_connections.remove(
                websocket
            )

        print(
            "[WS] Client disconnected "
            f"({len(self.active_connections)} active)"
        )

    async def broadcast(
        self,
        payload: dict,
    ):

        disconnected = []

        for connection in (
            self.active_connections
        ):

            try:

                await connection.send_json(
                    payload
                )

            except Exception as exc:

                print(
                    f"[WS] Send failed: {exc}"
                )

                disconnected.append(
                    connection
                )

        for connection in disconnected:

            self.disconnect(
                connection
            )

        if self.active_connections:

            print(
                "[WS] Broadcast cart update "
                f"to "
                f"{len(self.active_connections)} "
                "client(s)"
            )


manager = ConnectionManager()


# =========================================================
# REQUEST MODEL
# =========================================================

class CartRequest(BaseModel):

    product: str

    track_id: Optional[int] = None


# =========================================================
# PRODUCT MAP
# =========================================================

CLASS_TO_PRODUCT = {
    0: "everest",
    1: "mayo",
    2: "shampoo",
    3: "vaseline",
    4: "chocopie",
}


# =========================================================
# HELPERS
# =========================================================

def validate_product(
    product: str,
) -> str:

    product = (
        product
        .strip()
        .lower()
    )

    if product not in PRODUCTS:

        raise HTTPException(
            status_code=400,
            detail={
                "error": (
                    f"Unknown product: "
                    f"{product}"
                ),
                "valid_products": PRODUCTS,
            },
        )

    return product


def make_cart_payload(
    cart: dict,
    event: Optional[dict] = None,
) -> dict:

    return {
        "type": "cart_update",

        "cart": cart[
            "items"
        ],

        "total_items": cart[
            "total_items"
        ],

        "total": cart[
            "total"
        ],

        "last_event": (
            event
            if event is not None
            else cart[
                "last_event"
            ]
        ),
    }


# =========================================================
# CV → CART
# =========================================================

def handle_cv_transaction(
    event: dict,
    loop,
):
    """
    Convert a CV transaction into a cart update.

    Supported events:

        ADD
        REMOVE
    """

    action = event.get(
        "event"
    )

    if action not in {
        "ADD",
        "REMOVE",
    }:

        return

    product_class = event.get(
        "product_class"
    )

    track_id = event.get(
        "track_id"
    )

    product = CLASS_TO_PRODUCT.get(
        product_class
    )

    if product is None:

        print(
            "[TX] Unknown product class: "
            f"{product_class}"
        )

        return

    print(
        f"[TX] {action} "
        f"{product.upper()} "
        f"| Track {track_id}"
    )

    # -----------------------------------------------------
    # MODIFY AUTHORITATIVE CART
    # -----------------------------------------------------

    if action == "ADD":

        cart, cart_event = (
            cart_manager.add_item(
                product,
                track_id,
            )
        )

    else:

        cart, cart_event = (
            cart_manager.remove_item(
                product,
                track_id,
            )
        )

    # -----------------------------------------------------
    # IGNORE INVALID / DUPLICATE EVENTS
    # -----------------------------------------------------

    if cart_event.get(
        "event"
    ) != action:

        print(
            "[TX] Cart event was not applied: "
            f"{cart_event.get('event')}"
        )

        return

    print(
        f"[CART] {action} "
        f"{product.upper()} = "
        f"{cart['items'][product]}"
    )

    payload = make_cart_payload(
        cart,
        cart_event,
    )

    # -----------------------------------------------------
    # ASYNC WEBSOCKET BROADCAST
    # -----------------------------------------------------

    future = (
        asyncio.run_coroutine_threadsafe(
            manager.broadcast(
                payload
            ),
            loop,
        )
    )

    def broadcast_done(f):

        try:

            f.result()

        except Exception as exc:

            print(
                "[WS] Async broadcast failed: "
                f"{exc}"
            )

    future.add_done_callback(
        broadcast_done
    )


# =========================================================
# FRONTEND
# =========================================================

@app.get("/")
async def frontend():

    frontend_file = (
        FRONTEND_DIR
        / "index.html"
    )

    if not frontend_file.exists():

        raise HTTPException(
            status_code=500,
            detail=(
                "Frontend index.html "
                "not found."
            ),
        )

    return FileResponse(
        frontend_file
    )


# =========================================================
# HEALTH
# =========================================================

@app.get("/health")
async def health():

    return {
        "status": "ok",
        "service": "smartcart-backend",
    }


# =========================================================
# CART API
# =========================================================

@app.get("/api/cart")
async def get_cart():

    return cart_manager.get_cart()


@app.get("/api/cart/events")
async def get_events():

    cart = (
        cart_manager.get_cart()
    )

    return {
        "last_event": (
            cart["last_event"]
        ),
    }


@app.post("/api/cart/add")
async def add_cart_item(
    request: CartRequest,
):

    product = validate_product(
        request.product
    )

    cart, event = (
        cart_manager.add_item(
            product,
            request.track_id,
        )
    )

    payload = make_cart_payload(
        cart,
        event,
    )

    await manager.broadcast(
        payload
    )

    return payload


@app.post("/api/cart/remove")
async def remove_cart_item(
    request: CartRequest,
):

    product = validate_product(
        request.product
    )

    cart, event = (
        cart_manager.remove_item(
            product,
            request.track_id,
        )
    )

    payload = make_cart_payload(
        cart,
        event,
    )

    await manager.broadcast(
        payload
    )

    return payload


@app.post("/api/cart/reset")
async def reset_cart():

    cart, event = (
        cart_manager.reset_cart()
    )

    payload = make_cart_payload(
        cart,
        event,
    )

    await manager.broadcast(
        payload
    )

    return payload


# =========================================================
# VIDEO LIST
# =========================================================

@app.get("/api/videos")
async def list_videos():

    demo_videos = sorted(
        file.name
        for file in DEMO_VIDEOS_DIR.glob("*")
        if file.suffix.lower()
        in {
            ".mp4",
            ".mov",
            ".m4v",
        }
    )

    controlled_videos = sorted(
        file.name
        for file in CONTROLLED_VIDEOS_DIR.glob("*")
        if file.suffix.lower()
        in {
            ".mp4",
            ".mov",
            ".m4v",
        }
    )

    return {
        "demo": demo_videos,
        "controlled": controlled_videos,
    }


# =========================================================
# VIDEO STREAM
# =========================================================

@app.get("/video_feed")
async def video_feed(
    video: str,
):

    safe_filename = (
        Path(video).name
    )

    video_path = (
        DEMO_VIDEOS_DIR
        / safe_filename
    )

    if not video_path.exists():

        raise HTTPException(
            status_code=404,
            detail=(
                f"Demo video not found: "
                f"{safe_filename}"
            ),
        )

    if video_path.suffix.lower() not in {
        ".mp4",
        ".mov",
        ".m4v",
    }:

        raise HTTPException(
            status_code=400,
            detail=(
                "Unsupported video format."
            ),
        )

    # Every new demonstration starts with
    # a clean digital cart.
    cart, event = (
        cart_manager.reset_cart()
    )

    reset_payload = make_cart_payload(
        cart,
        event,
    )

    await manager.broadcast(
        reset_payload
    )

    loop = (
        asyncio.get_running_loop()
    )

    print(
        f"[VIDEO] Starting demo: "
        f"{safe_filename}"
    )

    return StreamingResponse(
        generate_mjpeg(
            str(video_path),
            event_callback=lambda event: (
                handle_cv_transaction(
                    event,
                    loop,
                )
            ),
        ),
        media_type=(
            "multipart/x-mixed-replace; "
            "boundary=frame"
        ),
        headers={
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
    )


# =========================================================
# WEBSOCKET
# =========================================================

@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
):

    await manager.connect(
        websocket
    )

    try:

        current_cart = (
            cart_manager.get_cart()
        )

        await websocket.send_json(
            make_cart_payload(
                current_cart,
                current_cart[
                    "last_event"
                ],
            )
        )

        while True:

            await websocket.receive_text()

    except WebSocketDisconnect:

        manager.disconnect(
            websocket
        )

    except Exception as exc:

        print(
            f"[WS] Error: {exc}"
        )

        manager.disconnect(
            websocket
        )
