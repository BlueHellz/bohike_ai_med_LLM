"""WebSocket stub for future real-time session channels."""

from fastapi import APIRouter, WebSocket

ws_router = APIRouter()


@ws_router.websocket("/ws/sessions/{session_id}")
async def session_ws(websocket: WebSocket, session_id: str):
    """WebSocket stub — use REST POST /api/v1/sessions/{id}/messages for turns."""
    await websocket.accept()
    await websocket.send_json(
        {"status": "stub", "message": "Use REST API for consultation turns", "session_id": session_id}
    )
    await websocket.close()
