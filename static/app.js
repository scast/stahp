var app = new Vue({
  el: '#app',
  data: {
    players: [],
    name: '',
    rounds: []
  },
  methods: {
    startRound: function() {
      ws.send(JSON.stringify({"type": "start_round"}));
    },
    stahpRound: function() {
      var round = this.rounds[this.rounds.length - 1];
      round.finished = true;
      ws.send(JSON.stringify({"type": "end_round", value: round.player}));
    }
  }
});


const ws = new WebSocket("wss://stahp-backend.onrender.com/ws");


// Connection opened
ws.addEventListener('open', function (event) {
  // ws.send(JSON.stringify({"type": "name", "value": "scb"}));
});

// Listen for messages
ws.addEventListener('message', function (event) {
  console.log('Message from server ', event.data);

  var data = JSON.parse(event.data);
  if (data.type === "players") {
    data.value.sort(function(x, y) {
      return y.score - x.score;
    });
    app.players = data.value;
  }

  if (data.type === "new_round") {
    app.rounds.push({
      letter: data.value,
      finished: false,
      player: {
        name: '',
        surname: '',
        country: '',
        food: '',
        animal: '',
        movie: '',
        object: '',
      }

    });
  }

  if (data.type === "finish_round") {
    if (app.rounds.length != 0) {
      var round = app.rounds[app.rounds.length - 1];
      round.finished = true;
      ws.send(JSON.stringify({"type": "end_round", value: round.player}));
    }
  }

});

app.$watch('name', function(newValue, oldValue) {
  ws.send(JSON.stringify({"type": "name", "value": newValue}));
});
