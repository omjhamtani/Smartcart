import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from threading import Lock


class CartManager:

    PRODUCTS = [
        "everest",
        "mayo",
        "shampoo",
        "vaseline",
        "chocopie",
    ]

    # Current prototype contains only one physical unit
    # of each product.
    MAX_QUANTITY = 1

    def __init__(
        self,
        cart_file: str | Path,
    ):

        self.cart_file = Path(
            cart_file
        )

        self.lock = Lock()

        self.state = {
            "session_id": "demo-session",

            "items": {
                product: 0
                for product in self.PRODUCTS
            },

            "total_items": 0,

            "total": None,

            "last_event": None,
        }

        self._load()

    # =====================================================
    # LOAD
    # =====================================================

    def _load(self):

        if not self.cart_file.exists():

            self.save_cart()

            return

        try:

            with self.cart_file.open(
                "r",
                encoding="utf-8",
            ) as f:

                loaded = json.load(f)

            items = loaded.get(
                "items",
                {},
            )

            for product in self.PRODUCTS:

                self.state["items"][product] = min(
                    self.MAX_QUANTITY,
                    max(
                        0,
                        int(
                            items.get(
                                product,
                                0,
                            )
                        ),
                    ),
                )

            self.state["session_id"] = (
                loaded.get(
                    "session_id",
                    "demo-session",
                )
            )

            self.state["total"] = (
                loaded.get("total")
            )

            self._recalculate()

        except (
            json.JSONDecodeError,
            OSError,
            ValueError,
        ) as exc:

            print(
                f"[CART] Failed to load cart.json: "
                f"{exc}"
            )

            print(
                "[CART] Starting with an empty cart."
            )

            self.save_cart()

    # =====================================================
    # RECALCULATE
    # =====================================================

    def _recalculate(self):

        self.state["total_items"] = sum(
            self.state["items"].values()
        )

    # =====================================================
    # SAVE
    # =====================================================

    def save_cart(self):

        self.cart_file.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with self.cart_file.open(
            "w",
            encoding="utf-8",
        ) as f:

            json.dump(
                self.state,
                f,
                indent=2,
            )

    # =====================================================
    # GET CART
    # =====================================================

    def get_cart(self):

        with self.lock:

            self._recalculate()

            return deepcopy(
                self.state
            )

    # =====================================================
    # ADD
    # =====================================================

    def add_item(
        self,
        product: str,
        track_id: int | None = None,
    ):

        product = product.lower()

        if product not in self.PRODUCTS:

            raise ValueError(
                f"Unknown product: {product}"
            )

        with self.lock:

            current_quantity = (
                self.state["items"][product]
            )

            # ---------------------------------------------
            # ONE-PRODUCT LIMIT
            # ---------------------------------------------

            if (
                current_quantity
                >= self.MAX_QUANTITY
            ):

                event = {
                    "event": "IGNORED_ADD",
                    "product": product,
                    "track_id": track_id,
                    "timestamp": datetime.now().isoformat(
                        timespec="seconds"
                    ),
                }

                self.state["last_event"] = event

                self.save_cart()

                print(
                    f"[CART] Ignored duplicate ADD "
                    f"{product}"
                )

                return (
                    deepcopy(self.state),
                    event,
                )

            self.state["items"][product] += 1

            self._recalculate()

            event = {
                "event": "ADD",
                "product": product,
                "track_id": track_id,
                "timestamp": datetime.now().isoformat(
                    timespec="seconds"
                ),
            }

            self.state["last_event"] = event

            self.save_cart()

            print(
                f"[CART] ADD {product} "
                f"→ {self.state['items'][product]}"
            )

            return (
                deepcopy(self.state),
                event,
            )

    # =====================================================
    # REMOVE
    # =====================================================

    def remove_item(
        self,
        product: str,
        track_id: int | None = None,
    ):

        product = product.lower()

        if product not in self.PRODUCTS:

            raise ValueError(
                f"Unknown product: {product}"
            )

        with self.lock:

            current_quantity = (
                self.state["items"][product]
            )

            if current_quantity <= 0:

                event = {
                    "event": "INVALID_REMOVE",
                    "product": product,
                    "track_id": track_id,
                    "timestamp": datetime.now().isoformat(
                        timespec="seconds"
                    ),
                }

                self.state["last_event"] = event

                self.save_cart()

                print(
                    f"[CART] Invalid REMOVE "
                    f"{product}"
                )

                return (
                    deepcopy(self.state),
                    event,
                )

            self.state["items"][product] -= 1

            self._recalculate()

            event = {
                "event": "REMOVE",
                "product": product,
                "track_id": track_id,
                "timestamp": datetime.now().isoformat(
                    timespec="seconds"
                ),
            }

            self.state["last_event"] = event

            self.save_cart()

            print(
                f"[CART] REMOVE {product} "
                f"→ {self.state['items'][product]}"
            )

            return (
                deepcopy(self.state),
                event,
            )

    # =====================================================
    # RESET
    # =====================================================

    def reset_cart(self):

        with self.lock:

            for product in self.PRODUCTS:

                self.state["items"][product] = 0

            self._recalculate()

            self.state["last_event"] = {
                "event": "RESET",
                "product": None,
                "track_id": None,
                "timestamp": datetime.now().isoformat(
                    timespec="seconds"
                ),
            }

            self.save_cart()

            print(
                "[CART] Cart reset"
            )

            return (
                deepcopy(self.state),
                self.state["last_event"],
            )
