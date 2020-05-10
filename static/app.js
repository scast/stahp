const ws = new WebSocket( "ws://localhost:8000/ws");

function sendMessage(type, value = null) {
  let obj = {type, value};
  console.log("sending", obj);
  ws.send(JSON.stringify(obj));
}

const PLAYING = "PLAYING";
const SCORING = "SCORING";
const REVIEWING = "REVIEWING";
const INITIALIZING = "INITIALIZING";

var app = new Vue({
  el: '#app',
  data: {
    players: [],
    name: '',
    rounds: [],
    previous_round: [],
    state: INITIALIZING,
    initialized: false,
    challenge: null,
    fields: [
      { id: "name",    display: "Name" },
      { id: "surname", display: "Surname/Last name" },
      { id: "country", display: "Country/City" },
      { id: "food",    display: "Food" },
      { id: "animal",  display: "Animal" },
      { id: "movie",   display: "Movie/TV Show" },
      { id: "song",    display: "Song" },
      { id: "brand",   display: "Brand" },
      { id: "company", display: "Company" },
      { id: "object",  display: "Object" },
    ]
  },
  watch: {
    name: function(newValue, oldValue) {
      if (this.initialized)
        this.sendName(newValue);
    }
  },

  methods: {
    startRound: function() {
      sendMessage("start_round");
      this.state = PLAYING;
    },

    stahpRound: function() {
      var round = this.rounds[this.rounds.length - 1];
      round.finished = true;
      sendMessage("end_round", round.player);
      this.state = SCORING;
    },

    doChallenge: function(word, field, score) {
      if (score > 0 && word){
        app.state = "WAITING_VOTE";
        sendMessage("challenge", {word, field});
      }
    },

    doVote: function(acceptWord) {
      sendMessage("vote", acceptWord);
      this.state = "WAITING_VOTE";
      this.challenge = null;
    },

    sendName: _.debounce(function(newName) {
      sendMessage("name", newName);
    }, 200),

    initialize: function(value) {
      this.name = value.name;
      this.state = value.state;
      this.initialized = true;
      console.log("initialized");
    },

  },

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

  if (data.type === "welcome") {
    app.initialize(data.value);
  }

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
      player: Object.fromEntries(app.fields.map(x=> [x.id, ""]))
    });
    app.previous_round = [];
  }

  if (data.type === "finish_round") {
    app.state = SCORING;
    if (app.rounds.length != 0) {
      var round = app.rounds[app.rounds.length - 1];
      round.finished = true;
      sendMessage("end_round", round.player);
    }
  }

  if (data.type === "round_score") {
    app.previous_round = data.value.round;
    app.rounds[app.rounds.length - 1].score = data.value.my_score;
    app.state = REVIEWING;
  }

  if (data.type === "challenge") {
    app.challenge = data.value;
    app.state = "VOTING";
  }

  if (data.type === "vote_result") {
    app.challenge = null;
    app.state = "REVIEWING";
  }
});
