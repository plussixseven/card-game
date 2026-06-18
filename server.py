import asyncio
import json
import os
import uuid
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from game_logic import CardGame

app = FastAPI()

# Лобби: room_id -> {'players': [ws_info], 'game': CardGame|None}
rooms = {}


class ConnectionManager:
    def __init__(self):
        self.connections = {}  # user_id -> websocket

    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        self.connections[user_id] = websocket

    def disconnect(self, user_id: str):
        self.connections.pop(user_id, None)

    async def send(self, user_id: str, data: dict):
        ws = self.connections.get(user_id)
        if ws:
            try:
                await ws.send_text(json.dumps(data, ensure_ascii=False))
            except Exception:
                pass

    async def broadcast(self, user_ids: list, data: dict):
        for uid in user_ids:
            await self.send(uid, data)


manager = ConnectionManager()


@app.get("/")
async def root():
    with open("static/index.html", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.websocket("/ws/{room_id}/{user_id}/{username}")
async def websocket_endpoint(websocket: WebSocket, room_id: str, user_id: str, username: str):
    await manager.connect(websocket, user_id)

    if room_id not in rooms:
        rooms[room_id] = {'players': [], 'game': None, 'usernames': {}}

    room = rooms[room_id]
    room['usernames'][user_id] = username

    if user_id not in [p['id'] for p in room['players']]:
        room['players'].append({'id': user_id, 'name': username})

    player_ids = [p['id'] for p in room['players']]

    # Уведомляем всех о новом игроке
    await manager.broadcast(player_ids, {
        'type': 'lobby',
        'players': [{'id': p['id'], 'name': p['name']} for p in room['players']],
        'room': room_id
    })

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            action = msg.get('action')

            if action == 'start' and room['game'] is None:
                if len(room['players']) < 2:
                    await manager.send(user_id, {'type': 'error', 'msg': 'Нужно минимум 2 игрока'})
                    continue
                room['game'] = CardGame(player_ids)
                game = room['game']
                gs = game.get_state()
                # Рассылаем начальное состояние каждому игроку с его рукой
                for pid in player_ids:
                    ps = game.get_state(for_player=pid)
                    await manager.send(pid, {
                        'type': 'start',
                        'state': ps,
                        'usernames': room['usernames']
                    })

            elif action == 'play' and room['game']:
                game = room['game']
                card_idx = msg.get('card_idx', -1)
                result = game.play_card(user_id, card_idx)

                if not result['ok']:
                    await manager.send(user_id, {'type': 'error', 'msg': result['msg']})
                    continue

                # Рассылаем обновление всем
                for pid in player_ids:
                    ps = game.get_state(for_player=pid)
                    await manager.send(pid, {
                        'type': 'update',
                        'state': ps,
                        'events': result['events'],
                        'usernames': room['usernames']
                    })

                if game.state == 'finished':
                    loser_name = room['usernames'].get(game.loser, game.loser)
                    await manager.broadcast(player_ids, {
                        'type': 'finished',
                        'loser': game.loser,
                        'loser_name': loser_name
                    })
                    room['game'] = None

            elif action == 'rematch':
                room['game'] = None
                await manager.broadcast(player_ids, {'type': 'lobby', 'players': room['players'], 'room': room_id})

    except WebSocketDisconnect:
        manager.disconnect(user_id)
        room['players'] = [p for p in room['players'] if p['id'] != user_id]
        await manager.broadcast(
            [p['id'] for p in room['players']],
            {'type': 'lobby', 'players': room['players'], 'room': room_id}
        )


app.mount("/static", StaticFiles(directory="static"), name="static")
