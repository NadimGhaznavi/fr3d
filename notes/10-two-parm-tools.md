{
  "name": "submit_epsilon_pair",
  "description": "Submit a new pair of epsilon initial and decay values.",
  "parameters": {
    "type": "object",
    "properties": {
      "initial": { "type": "number", "enum": [0.91, 0.96, 0.99] },
      "decay": { "type": "number", "enum": [0.95, 0.97, 0.99] }
    },
    "required": ["initial", "decay"]
  }
}