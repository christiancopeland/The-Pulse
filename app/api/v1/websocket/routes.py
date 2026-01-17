# External imports
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import List, Optional
import json
import logging

# Internal imports
from app.services.research_assistant import ResearchAssistant
from app.services.broadcast import (
    get_broadcast_manager,
    EventType,
    BroadcastEvent,
)


router = APIRouter()
logger = logging.getLogger(__name__)

# Initialize services
research_assistant = ResearchAssistant()

# Get broadcast manager for event broadcasting
broadcast_manager = get_broadcast_manager()

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    # Register with broadcast manager for event broadcasting
    client_id = await broadcast_manager.connect(websocket)

    try:
        while True:
            data = await websocket.receive_text()
            logger.debug(f"Received WebSocket message: {data[:100]}...")

            message_data = json.loads(data)

            # Handle subscription requests
            if message_data.get('type') == 'subscribe':
                event_types = message_data.get('events', [])
                try:
                    events = [EventType(e) for e in event_types]
                    await broadcast_manager.subscribe(client_id, events)
                    await websocket.send_json({
                        "type": "subscribed",
                        "events": event_types
                    })
                except ValueError as e:
                    await websocket.send_json({
                        "type": "error",
                        "error": f"Invalid event type: {e}"
                    })
                continue

            # Handle unsubscription requests
            if message_data.get('type') == 'unsubscribe':
                event_types = message_data.get('events', [])
                try:
                    if event_types:
                        events = [EventType(e) for e in event_types]
                        await broadcast_manager.unsubscribe(client_id, events)
                    else:
                        await broadcast_manager.unsubscribe(client_id)
                    await websocket.send_json({
                        "type": "unsubscribed",
                        "events": event_types or "all"
                    })
                except ValueError as e:
                    await websocket.send_json({
                        "type": "error",
                        "error": f"Invalid event type: {e}"
                    })
                continue

            # Handle get recent events request
            if message_data.get('type') == 'get_events':
                event_types = message_data.get('events', [])
                limit = message_data.get('limit', 10)
                try:
                    events = None
                    if event_types:
                        events = [EventType(e) for e in event_types]
                    recent = broadcast_manager.get_recent_events(events, limit)
                    await websocket.send_json({
                        "type": "events",
                        "events": [e.to_dict() for e in recent]
                    })
                except ValueError as e:
                    await websocket.send_json({
                        "type": "error",
                        "error": f"Invalid event type: {e}"
                    })
                continue

            # Check message type
            if message_data.get('type') == 'command':
                # Handle command messages
                command = message_data.get('command')
                payload = message_data.get('payload', {})
                logger.debug(f"Received command: {command} with payload: {payload}")
                
                # Handle project_context command
                if command == 'project_context':
                    await websocket.send_json({
                        "type": "command_response",
                        "command": command,
                        "status": "success",
                        "payload": payload
                    })
                    continue
                
                # Add entity tracking commands
                # if command == 'track_entity':
                #     # Initialize services
                #     async with async_session() as session:
                #         entity_tracker = EntityTrackingService(session, document_processor)
                        
                #         try:
                #             entity = await entity_tracker.add_tracked_entity(
                #                 name=payload['name'],
                #                 entity_type=payload.get('type', 'CUSTOM'),
                #                 metadata=payload.get('metadata')
                #             )
                            
                #             await websocket.send_json({
                #                 "type": "command_response",
                #                 "command": command,
                #                 "status": "success",
                #                 "data": {
                #                     "entity_id": str(entity.entity_id),
                #                     "name": entity.name
                #                 }
                #             })
                #         except Exception as e:
                #             await websocket.send_json({
                #                 "type": "error",
                #                 "command": command,
                #                 "error": str(e)
                #             })
                
                # elif command == 'get_entity_mentions':
                #     async with async_session() as session:
                #         entity_tracker = EntityTrackingService(session, document_processor)
                        
                #         try:
                #             mentions = await entity_tracker.get_entity_mentions(
                #                 entity_name=payload['name'],
                #                 limit=payload.get('limit', 50),
                #                 offset=payload.get('offset', 0)
                #             )
                            
                #             await websocket.send_json({
                #                 "type": "command_response",
                #                 "command": command,
                #                 "status": "success",
                #                 "data": mentions
                #             })
                #         except Exception as e:
                #             await websocket.send_json({
                #                 "type": "error",
                #                 "command": command,
                #                 "error": str(e)
                #             })
            
            # Handle chat messages using research assistant
            elif message_data.get('type') == 'chat':
                try:
                    messages_data = message_data.get('messages', [])
                    if not messages_data:
                        await websocket.send_json({
                            "type": "error",
                            "error": "No messages found in request"
                        })
                        continue
                    
                    # Process messages directly (no Message class conversion needed)
                    async for chunk in research_assistant.chat(messages_data):
                        if isinstance(chunk, dict):
                            await websocket.send_json(chunk)
                        else:
                            logger.debug(f"Unexpected chunk format: {chunk}")
                            
                except Exception as e:
                    logger.error(f"Error processing chat: {str(e)}")
                    await websocket.send_json({
                        "type": "error",
                        "error": f"Error processing chat: {str(e)}"
                    })

    except WebSocketDisconnect:
        await broadcast_manager.disconnect(client_id)
        logger.debug(f"WebSocket disconnected: {client_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {str(e)}")
        try:
            await websocket.send_json({
                "type": "error",
                "error": str(e)
            })
        except Exception:
            pass  # Connection may be closed
        finally:
            await broadcast_manager.disconnect(client_id)