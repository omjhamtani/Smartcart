from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

MODEL_PATH = BASE_DIR / "model" / "best.pt"

VIDEOS_DIR = BASE_DIR / "videos"
DEMO_VIDEOS_DIR = VIDEOS_DIR / "demo"
CONTROLLED_VIDEOS_DIR = VIDEOS_DIR / "controlled"

CART_FILE = BASE_DIR / "backend" / "cart.json"

CLASS_NAMES = {
    0: "everest",
    1: "mayo",
    2: "shampoo",
    3: "vaseline",
    4: "chocopie",
}

PRODUCTS = list(CLASS_NAMES.values())

HOST = "127.0.0.1"
PORT = 8000
