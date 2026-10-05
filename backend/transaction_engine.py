from dataclasses import dataclass
from typing import Optional

from config import CLASS_NAMES


# =========================================================
# TRANSACTION SETTINGS
# =========================================================

# Product must remain absent for this long before it is
# considered a genuine pickup.
ABSENCE_SECONDS = 2.5

# Product must remain continuously visible for this long
# after being in the cart before we consider it returned.
RETURN_CONFIRM_SECONDS = 0.8

# Minimum observations required before we trust that
# the product was actually present in the scene.
MIN_OBSERVATIONS = 10

# Minimum consecutive visible frames for return confirmation.
RETURN_MIN_FRAMES = 8


# =========================================================
# PRODUCT STATE
# =========================================================

@dataclass
class ProductState:

    class_id: int

    state: str = "UNINITIALIZED"

    initialized: bool = False

    observations: int = 0

    last_seen: Optional[float] = None

    missing_since: Optional[float] = None

    visible_since: Optional[float] = None

    visible_streak: int = 0

    last_track_id: Optional[int] = None


# =========================================================
# TRANSACTION ENGINE
# =========================================================

class TransactionEngine:

    def __init__(
        self,
        absence_seconds: float = ABSENCE_SECONDS,
        return_confirm_seconds: float = RETURN_CONFIRM_SECONDS,
        min_observations: int = MIN_OBSERVATIONS,
        return_min_frames: int = RETURN_MIN_FRAMES,
    ):

        self.absence_seconds = absence_seconds
        self.return_confirm_seconds = return_confirm_seconds
        self.min_observations = min_observations
        self.return_min_frames = return_min_frames

        self.products = {
            class_id: ProductState(
                class_id=class_id
            )
            for class_id in CLASS_NAMES
        }

        print(
            "[TX] Transaction engine initialized"
        )

        print(
            f"[TX] Pickup absence threshold: "
            f"{self.absence_seconds:.1f}s"
        )

        print(
            f"[TX] Return confirmation: "
            f"{self.return_confirm_seconds:.1f}s"
        )

    # =====================================================
    # FRAME UPDATE
    # =====================================================

    def update(
        self,
        detections: list[dict],
        timestamp: float,
    ) -> list[dict]:
        """
        Update product states using detections from one frame.

        Detection format:

        {
            "track_id": 17,
            "class_id": 1,
            "confidence": 0.97
        }

        Returns transaction events:

        {
            "event": "ADD",
            "product_class": 1,
            "track_id": 17,
            ...
        }

        or:

        {
            "event": "REMOVE",
            "product_class": 1,
            "track_id": 31,
            ...
        }
        """

        events = []

        # -------------------------------------------------
        # Aggregate detections by product class.
        #
        # Since the prototype has one physical unit of each
        # product, we care about whether a product class is
        # visible rather than how many duplicate boxes YOLO
        # produced.
        # -------------------------------------------------

        visible_products: dict[int, dict] = {}

        for detection in detections:

            track_id = detection.get(
                "track_id"
            )

            class_id = detection.get(
                "class_id"
            )

            confidence = float(
                detection.get(
                    "confidence",
                    0.0
                )
            )

            if class_id is None:
                continue

            class_id = int(class_id)

            if class_id not in self.products:
                continue

            # Ignore detections without a tracker ID for
            # transaction logic. YOLO can still display them.
            if track_id is None:
                continue

            # Keep the strongest detection for each product.
            existing = visible_products.get(
                class_id
            )

            if (
                existing is None
                or confidence > existing["confidence"]
            ):

                visible_products[class_id] = {
                    "track_id": int(track_id),
                    "confidence": confidence,
                }

        # -------------------------------------------------
        # UPDATE EVERY PRODUCT
        # -------------------------------------------------

        for class_id, product_state in self.products.items():

            visible = (
                class_id in visible_products
            )

            detection = visible_products.get(
                class_id
            )

            # =================================================
            # INITIALIZATION
            # =================================================

            if not product_state.initialized:

                if visible:

                    product_state.observations += 1

                    product_state.last_seen = (
                        timestamp
                    )

                    product_state.last_track_id = (
                        detection["track_id"]
                    )

                    if (
                        product_state.observations
                        >= self.min_observations
                    ):

                        product_state.initialized = True

                        product_state.state = (
                            "ON_SHELF"
                        )

                        print(
                            "[TX] Initialized "
                            f"{CLASS_NAMES[class_id]} "
                            "as ON_SHELF"
                        )

                continue

            # =================================================
            # ON SHELF
            # =================================================

            if product_state.state == "ON_SHELF":

                if visible:

                    product_state.last_seen = (
                        timestamp
                    )

                    product_state.last_track_id = (
                        detection["track_id"]
                    )

                    # Product came back before the pickup
                    # threshold. Cancel pending absence.
                    product_state.missing_since = None

                    continue

                # Product is not visible.

                if product_state.missing_since is None:

                    product_state.missing_since = (
                        timestamp
                    )

                    print(
                        "[TX] "
                        f"{CLASS_NAMES[class_id]} "
                        "started missing"
                    )

                    continue

                missing_for = (
                    timestamp
                    - product_state.missing_since
                )

                # -------------------------------------------------
                # GENUINE PICKUP
                # -------------------------------------------------

                if missing_for >= self.absence_seconds:

                    event = {
                        "event": "ADD",
                        "product_class": class_id,
                        "track_id": (
                            product_state.last_track_id
                        ),
                        "timestamp": timestamp,
                        "missing_for": round(
                            missing_for,
                            2
                        ),
                    }

                    events.append(event)

                    product_state.state = (
                        "IN_CART"
                    )

                    product_state.missing_since = None

                    product_state.visible_since = None

                    product_state.visible_streak = 0

                    print(
                        "[TX] ADD "
                        f"{CLASS_NAMES[class_id].upper()} "
                        f"| Track "
                        f"{product_state.last_track_id} "
                        f"| Missing "
                        f"{missing_for:.2f}s"
                    )

                continue

            # =================================================
            # IN CART
            # =================================================

            if product_state.state == "IN_CART":

                if not visible:

                    # It is still out of the camera view.
                    # This is normal for an item already
                    # considered to be in the cart.
                    product_state.visible_since = None

                    product_state.visible_streak = 0

                    continue

                # -------------------------------------------------
                # PRODUCT HAS REAPPEARED
                # -------------------------------------------------

                product_state.last_seen = (
                    timestamp
                )

                product_state.last_track_id = (
                    detection["track_id"]
                )

                if product_state.visible_since is None:

                    product_state.visible_since = (
                        timestamp
                    )

                    product_state.visible_streak = 1

                    print(
                        "[TX] Possible return "
                        f"{CLASS_NAMES[class_id]} "
                        f"| Track "
                        f"{detection['track_id']}"
                    )

                else:

                    product_state.visible_streak += 1

                visible_for = (
                    timestamp
                    - product_state.visible_since
                )

                # -------------------------------------------------
                # CONFIRMED RETURN TO SHELF
                # -------------------------------------------------

                if (
                    visible_for
                    >= self.return_confirm_seconds
                    and
                    product_state.visible_streak
                    >= self.return_min_frames
                ):

                    event = {
                        "event": "REMOVE",
                        "product_class": class_id,
                        "track_id": (
                            detection["track_id"]
                        ),
                        "timestamp": timestamp,
                        "visible_for": round(
                            visible_for,
                            2
                        ),
                    }

                    events.append(event)

                    product_state.state = (
                        "ON_SHELF"
                    )

                    product_state.visible_since = None

                    product_state.visible_streak = 0

                    product_state.missing_since = None

                    print(
                        "[TX] REMOVE "
                        f"{CLASS_NAMES[class_id].upper()} "
                        f"| Track "
                        f"{detection['track_id']} "
                        f"| Visible "
                        f"{visible_for:.2f}s"
                    )

        return events

    # =====================================================
    # DEBUG
    # =====================================================

    def get_debug_state(self):

        result = []

        for class_id, state in self.products.items():

            result.append(
                {
                    "product": CLASS_NAMES[class_id],
                    "class_id": class_id,
                    "state": state.state,
                    "initialized": state.initialized,
                    "observations": state.observations,
                    "last_seen": state.last_seen,
                    "missing_since": state.missing_since,
                    "visible_since": state.visible_since,
                    "visible_streak": state.visible_streak,
                    "last_track_id": state.last_track_id,
                }
            )

        return result
