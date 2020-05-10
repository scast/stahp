import asyncio
import json
import logging
import petname
import random
import string
import unidecode

from collections import defaultdict, Counter
from aiohttp import WSMsgType, web

logger = logging.getLogger("stahp")


class Player:
    def __init__(self, ws, stahp, count):
        self.ws = ws
        self.name = petname.generate()
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

                print(f"received {data}")

                if data["type"] == "name":
                    logger.info("setting username to %s", data["value"])
                    self.name = data["value"]
                    await self.stahp.broadcast_names()

                if data["type"] == "challenge":
                    if self.stahp.state == REVIEWING:
                        await self.stahp.challenge(self, data["value"]["word"], data["value"]["field"])

                if data["type"] == "vote":
                    if self.stahp.state == VOTING:
                        await self.stahp.vote(self, data["value"])


                if data["type"] == "start_round":
                    if self.stahp.state == REVIEWING:
                        await self.stahp.start_round()

                if data["type"] == "end_round":
                    if self.stahp.state == PLAYING:
                        await self.stahp.end_round(self, data["value"])

                    elif self.stahp.state == SCORING:
                        await self.stahp.finish_round(self, data["value"])

        print(f"removing player {self.count}")
        self.stahp.players.pop(self.count)
        await self.stahp.broadcast_names()


    async def welcome(self):
        await self.send_message("welcome", {
            "name": self.name,
            "state": self.stahp.state
        })

    async def send_json(self, data):
        print("sending", data)
        await self.ws.send_str(json.dumps(data))

    async def send_message(self, type_, value=None):
        await self.send_json({"type": type_, "value": value})

    def __str__(self):
        return f"<Player {self.count} {self.name}>"

PLAYING = "PLAYING"
SCORING = "SCORING"
REVIEWING = "REVIEWING"
VOTING = "VOTING"

class Stahp:
    def __init__(self):
        self.players = {}
        self.player_count = 0
        self.state = REVIEWING
        self.reset()

    def reset(self):
        self.used = set()
        self.round_results = {}
        self.scores = defaultdict(int)

    async def handle_player(self, ws):
        logging.info("accepting new connection")
        player = self.players[self.player_count] = Player(
            ws, self, self.player_count
        )
        print(f"players: {self.players}")
        self.player_count += 1
        await player.welcome()
        await self.broadcast_names()
        await player.command()

    async def broadcast_names(self):
        data = [
            {"name": p.name, "score": self.scores[p.count]}
            for p in self.players.values()
        ]

        for p in self.players.values():
            await p.send_message("players", data)


    async def start_round(self):
        assert self.state == REVIEWING
        self.state = PLAYING

        print(f"New round without {self.used}")
        letter = random.choice(list(set(string.ascii_uppercase) - self.used))
        self.used.add(letter)
        self.round_results = {}
        self.on_going_round = True
        self.letter = letter
        self.challenged_words = defaultdict(list)
        for p in self.players.values():
            await p.send_message("new_round", letter)

    async def challenge(self, player, word, field):
        assert self.state == REVIEWING
        self.state = VOTING
        self.votes = {}
        self.challenge_word = word
        self.challenge_field = field
        self.challenger = player.count

        for p in self.players.values():
            if p != player:
                await p.send_message("challenge", {
                    "from": p.name,
                    "word": word,
                    "field": field
                })

        print(f"CHALLENGE {word} {field}")

    async def vote(self, player, value):
        assert self.state == VOTING
        self.votes[player.count] = value
        await self.maybe_count_votes()

    async def maybe_count_votes(self):
        print(f"results={self.votes} challenger={self.challenger} players={self.players.keys()}")
        remaining_votes = list( set(self.players.keys()) - set(self.votes.keys()) )
        if remaining_votes == [self.challenger]:
            tally = Counter(self.votes.values())
            if tally[False] > tally[True]:
                self.challenged_words[self.challenge_field].append(self.challenge_word)
                await self.end_vote(True)
                await self.score_round()
                await self.broadcast_names()
            else:
                await self.end_vote(False)


    async def end_vote(self, result):
        assert self.state == VOTING
        for p in self.players.values():
            await p.send_message("vote_result", result)
        self.state = REVIEWING


    async def end_round(self, player, state):
        assert self.state == PLAYING
        self.state = SCORING

        self.round_results[player.count] = state
        for p in self.players.values():
            if p != player:
                await p.send_message("finish_round")

        await self.maybe_score_round()

    async def finish_round(self, player, data):
        self.round_results[player.count] = data
        await self.maybe_score_round()

    async def maybe_score_round(self):
        #print(f"results={self.round_results} players={self.players.keys()}")
        missing_scores = self.round_results.keys() != self.players.keys()
        if not missing_scores:
            await self.score_round()

    async def score_round(self, recount=False):
        def clean_value(s):
            return unidecode.unidecode(s.strip().lower())

        ans = defaultdict(dict)
        for r in self.round_results.values():
            for col, value in r.items():
                value = clean_value(value)
                if not value or len(value) < 2:
                    continue

                if value[0].lower() == self.letter.lower():
                    if value in self.challenged_words[col]:
                        ans[col][value] = 0
                    elif value in ans[col]:
                        ans[col][value] = 50
                    else:
                        ans[col][value] = 100

        scores = {}
        responses = {}
        for p, player in self.players.items():
            result = self.round_results.get(p)
            responses[p] = {}
            total_score = 0
            if result is not None:
                for col, value in result.items():
                    score = ans[col].get(clean_value(value), 0)
                    total_score += score
                    responses[p][col] = [value, score]

            scores[p] = total_score

        data = [
            {
                "name": player.name or p,
                "answers": responses.get(p),
                "score": scores[p],
            }
            for p, player in self.players.items()
        ]

        for p in self.players.values():
            await p.send_message("round_score", {
                "round": data,
                "my_score": scores[p.count]
            })

        # TODO: Fix total score after challenge
        for p in self.players:
            self.scores[p] += scores[p]

        await self.broadcast_names()
        self.state = REVIEWING


async def websocket_handler(request):
    ws = web.WebSocketResponse()
    stahp = app["stahp"]
    await ws.prepare(request)
    await stahp.handle_player(ws)
    return ws


async def on_startup(app):
    app["stahp"] = Stahp()

app = web.Application()
app.on_startup.append(on_startup)
app.add_routes([web.get("/ws", websocket_handler)])

if __name__ == "__main__":
    logging.basicConfig(level="INFO")
    web.run_app(app, port=9999)
