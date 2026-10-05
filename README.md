# SmartCart

SmartCart is a computer-vision-assisted checkout prototype. It processes demonstration videos with a YOLO object-detection model and ByteTrack tracking, infers when supported products are picked up or returned, and keeps a live digital cart synchronized with a browser dashboard.

The prototype currently supports one physical unit of each product:

- Everest
- Mayo
- Shampoo
- Vaseline
- Chocopie

## Features

- YOLO inference with ByteTrack object tracking.
- Automatic `ADD` events when a product disappears from view for the configured pickup threshold.
- Automatic `REMOVE` events when an item already in the cart becomes continuously visible again.
- FastAPI backend with REST endpoints, WebSocket updates, and an MJPEG video stream.
- Browser dashboard showing the live vision feed, cart contents, item count, last transaction, and connection status.
- JSON-backed cart persistence for the demo session.
- Manual cart add, remove, and reset endpoints for testing.

## Architecture

```text
                         +----------------------+
                         |  frontend/index.html |
                         |  app.js + styles.css  |
                         +----------+-----------+
                                    |
                REST / WebSocket / MJPEG video feed
                                    |
                         +----------v-----------+
                         |    backend/main.py   |
                         |   FastAPI application |
                         +-----+------------+----+
                               |            |
                 cart events   |            | video frames
                               |            |
                 +-------------v--+   +-----v----------------+
                 | cart_manager.py|   |     cv_engine.py     |
                 | JSON cart state |   | OpenCV + YOLO +      |
                 | and validation  |   | ByteTrack processing |
                 +-----------------+   +----------+-----------+
                                                  |
                                          detections per frame
                                                  |
                                      +-----------v------------+
                                      | transaction_engine.py  |
                                      | pickup/return state    |
                                      | machine and events     |
                                      +------------------------+
```

### Runtime flow

1. The browser loads the static dashboard from FastAPI at `/`.
2. `frontend/app.js` connects to `/ws`, loads available demonstration videos from `/api/videos`, and initializes the cart display.
3. Selecting a demo requests `/video_feed?video=<filename>`.
4. `cv_engine.generate_mjpeg()` opens the video with OpenCV, runs the bundled `model/best.pt` model through Ultralytics YOLO tracking, draws detections, and emits an MJPEG stream.
5. `TransactionEngine` aggregates tracked detections by product class. It emits `ADD` after a product is absent for 2.5 seconds and `REMOVE` after it is visible again for at least 0.8 seconds and 8 frames.
6. `main.py` converts those events into cart mutations through `CartManager`, persists the result to `backend/cart.json`, and broadcasts updates to connected WebSocket clients.

## Repository layout

```text
backend/
  main.py                 FastAPI app, REST routes, WebSocket manager, video endpoint
  cart_manager.py         Thread-safe JSON-backed cart state and cart mutations
  config.py               Paths, product/class mappings, host and port constants
  cv_engine.py            OpenCV video loop, YOLO inference, ByteTrack, overlays, MJPEG
  transaction_engine.py   Product state machine for pickup and return detection
  zones.py                Notes that spatial zones are currently disabled
  cart.json               Persisted demo cart state
  requirements.txt        Python runtime dependencies
  .gitignore              Python virtualenv/cache ignores
frontend/
  index.html              Dashboard markup
  app.js                  REST/WebSocket/video-feed client logic
  styles.css              Responsive dark dashboard styling
model/
  best.pt                 Trained Ultralytics model weights
README.md                 Project documentation
```

## Stack

- **Backend:** Python, FastAPI, Uvicorn, Pydantic
- **Computer vision:** Ultralytics YOLO, ByteTrack, OpenCV, PyTorch
- **Frontend:** Vanilla HTML, JavaScript, and CSS
- **Persistence:** Local JSON file (`backend/cart.json`)
- **Model:** `model/best.pt`

## Requirements

- Python 3.10+ recommended.
- A machine capable of running PyTorch and OpenCV.
- The repository's `model/best.pt` weights.
- Demonstration videos placed in `videos/demo/`.
- Optional controlled videos placed in `videos/controlled/`; the backend lists them, although the current `/video_feed` route streams only from `videos/demo/`.

## Installation

From the repository root:

```bash
cd backend
python -m venv venv
```

Activate the virtual environment:

```bash
# macOS/Linux
source venv/bin/activate

# Windows PowerShell
.\venv\Scripts\Activate.ps1
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Create the video directories and add supported video files (`.mp4`, `.mov`, or `.m4v`):

```bash
cd ..
mkdir -p videos/demo videos/controlled
```

On Windows, create the directories manually if `mkdir -p` is unavailable.

## Run the application

Start the FastAPI server from the `backend/` directory:

```bash
cd backend
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Open the dashboard at:

```text
http://127.0.0.1:8000/
```

The frontend is served by the backend, so it does not need a separate development server. The browser client currently expects the backend at `http://127.0.0.1:8000` and the WebSocket at `ws://127.0.0.1:8000/ws`.

## API

### Health

```http
GET /health
```

Returns the service status.

### Cart

```http
GET  /api/cart
GET  /api/cart/events
POST /api/cart/add
POST /api/cart/remove
POST /api/cart/reset
```

The add and remove endpoints accept JSON like:

```json
{
  "product": "mayo",
  "track_id": 17
}
```

Valid products are `everest`, `mayo`, `shampoo`, `vaseline`, and `chocopie`.

### Videos

```http
GET /api/videos
GET /video_feed?video=<filename>
```

`/api/videos` returns demo and controlled video filenames. `/video_feed` resets the cart before starting a demonstration and streams processed frames as `multipart/x-mixed-replace` MJPEG.

### WebSocket

```text
ws://127.0.0.1:8000/ws
```

Clients receive cart update messages shaped like:

```json
{
  "type": "cart_update",
  "cart": {
    "everest": 0,
    "mayo": 1,
    "shampoo": 0,
    "vaseline": 0,
    "chocopie": 0
  },
  "total_items": 1,
  "total": null,
  "last_event": {
    "event": "ADD",
    "product": "mayo",
    "track_id": 17,
    "timestamp": "2026-10-05T12:00:00"
  }
}
```

## Computer-vision transaction logic

`TransactionEngine` tracks one state per product class:

- `UNINITIALIZED`: waits for at least 10 valid tracked observations.
- `ON_SHELF`: product is visible and available for pickup.
- `IN_CART`: product has disappeared long enough to count as picked up.

Current thresholds are defined near the top of `backend/transaction_engine.py`:

- Pickup absence: `2.5` seconds.
- Return confirmation: `0.8` seconds.
- Initialization: `10` observations.
- Return confirmation: `8` consecutive visible frames.

Detections without a tracker ID are displayed by the CV overlay but ignored by transaction logic. Multiple detections for the same product class are reduced to the highest-confidence detection because the prototype models one physical unit per product.

## Configuration

Most configuration is centralized in `backend/config.py`:

- `MODEL_PATH`: `model/best.pt`
- `DEMO_VIDEOS_DIR`: `videos/demo`
- `CONTROLLED_VIDEOS_DIR`: `videos/controlled`
- `CART_FILE`: `backend/cart.json`
- `CLASS_NAMES`: numeric model classes mapped to product names
- `HOST` and `PORT`: default server values

The current implementation uses permissive CORS (`allow_origins=["*"]`) and hard-coded localhost URLs in the frontend, which are suitable for a local prototype but should be tightened before deployment.

## Current limitations

- The cart supports a maximum quantity of one for each product.
- Prices are not implemented, so `total` remains `null` and the UI displays `₹—`.
- The video endpoint currently reads only from `videos/demo/` even though the API lists controlled videos separately.
- There are no automated tests, lockfiles, CI workflows, or production deployment configuration in the repository.
- Spatial zones are intentionally disabled; pickup and return decisions are based on product visibility and disappearance timing.
- The frontend reconnects to a fixed localhost backend and is not configured for environment-specific URLs.

## Troubleshooting

- **No videos appear:** ensure files with `.mp4`, `.mov`, or `.m4v` extensions are inside `videos/demo/`.
- **Model loading fails:** verify that `model/best.pt` exists and that the installed PyTorch/Ultralytics stack supports the host machine.
- **The dashboard shows disconnected:** confirm the Uvicorn server is running on `127.0.0.1:8000` and that `/ws` is reachable.
- **Transactions do not fire:** use videos where the supported products are visible long enough to initialize and disappear/reappear according to the thresholds above.
- **Cart state is stale:** stop the server or use the Reset button, then inspect `backend/cart.json`.

## License

No license file is currently included in the repository.
