"""Placeholder for Pub/Sub event handlers."""
from fastapi import APIRouter, HTTPException, status

router = APIRouter()


@router.post("/events/{event_name}")
async def handle_event(event_name: str):
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Event handling not implemented in this slice")
