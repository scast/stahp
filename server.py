import asyncio
import json
import logging
import random
import string
from collections import defaultdict

from aiohttp import WSMsgType, web

logger = logging.getLogger("stahp")


class Player:
    def __init__(self, ws, stahp, count):
        self.ws = ws
        self.name = ""
        self.stahp = stahp
        self.count = count

    async def command(self):
        async for msg in self.ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)

                except Exception as exc:
                    logger.exception(exc)
                    continue

                if data["type"] == "name":
                    logger.info("setting username to %s", data["value"])
                    self.name = data["value"]
                    await self.stahp.broadcast_name(self)

                if data["type"] == "start_round":
                    if not self.stahp.on_going_round:
                        await self.stahp.start_round()

                if data["type"] == "end_round":
                    if self.stahp.on_going_round:
                        await self.stahp.end_round(self, data["value"])

                    if self.stahp.finishing:
                        await self.stahp.finish_round(self, data["value"])

        self.stahp.players.pop(self.count)

    async def send_json(self, data):
        await self.ws.send_str(json.dumps(data))


class Stahp:
    def __init__(self):
        self.players = {}
        self.player_count = 0
        self.used = set()
        self.on_going_round = False
        self.round_results = {}
        self.scores = defaultdict(int)

    async def handle_player(self, ws):
        logging.info("accepting new connection")
        player = self.players[self.player_count] = Player(
            ws, self, self.player_count
        )
        self.player_count += 1
        await player.send_json(
            {
                "type": "players",
                "value": [(p.name or p.count) for p in self.players.values()],
            }
        )
        await player.command()

    async def broadcast_name(self, player):
        data = [(p.name or p.count) for p in self.players.values()]
        for p in self.players.values():
            await p.send_json(
                {"type": "players", "value": data,}
            )

    async def start_round(self):
        letter = random.choice(list(set(string.ascii_uppercase) - self.used))
        self.round_results = {}
        self.on_going_round = True
        self.letter = letter
        for p in self.players.values():
            await p.send_json({"type": "new_round", "value": letter})

    async def end_round(self, player, state):
        self.on_going_round = False
        self.round_results[player.count] = state
        self.finishing = True
        for p in self.players.values():
            if p != player:
                await p.send_json({"type": "finish_round"})

        await asyncio.sleep(5)
        self.finishing = False
        await self.score_round()

    async def finish_round(self, player, data):
        self.round_results[player.count] = data

    async def score_round(self):
        ans = defaultdict(dict)
        for r in self.round_results.values():
            for col, value in r.items():
                value = value.strip().lower()
                if value[0].lower() == self.letter.lower():
                    if value in ans[col]:
                        ans[col][value] = 50
                    else:
                        ans[col][value] = 100

        scores = {}
        for p, player in self.players.items():
            result = self.round_results.get(p)
            score = 0
            if result is not None:
                for col, value in result.items():
                    if value in ans[col]:
                        score += ans[col][value]

            scores[p] = score

        data = [
            {
                "name": player.name or p,
                "answers": self.round_results.get(p),
                "score": scores[p],
            }
            for p, player in self.players.items()
        ]

        for p in self.players.values():
            await p.send_json({"type": "round_score", "value": data})

        for p in self.players:
            self.scores[p] += scores[p]

        data = [
            {"name": player.name or p.count, "score": self.scores[p],}
            for p, player in self.players.items()
        ]

        for p in self.players.values():
            await p.send_json({"type": "scores", "value": data})


async def websocket_handler(request):
    ws = web.WebSocketResponse()
    stahp = app["stahp"]
    await ws.prepare(request)
    await stahp.handle_player(ws)
    return ws


async def on_startup(app):
    app["stahp"] = Stahp()


if __name__ == "__main__":
    logging.basicConfig(level="INFO")
    app = web.Application()
    app.on_startup.append(on_startup)
    app.add_routes([web.get("/ws", websocket_handler)])
    web.run_app(app, port=9999)
