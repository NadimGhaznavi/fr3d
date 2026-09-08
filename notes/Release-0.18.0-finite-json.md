# Release v0.18.0 Spec

## Overview

The purpose of this release is to integrate the Snake Lab JSON schema metadata into the LLM prompts. The schema has been modified to constrain the number of valid configurations to a finite number (11,664).

## Final State

Fr3d should exit gracefully once all 11,664 configurations exist.

## Customizing Prompts

This section outlines how to handle the difference schema parameter.

## Const Example

```
    "epochs": {
      "title": "Number of epochs",
      "description": "Number of complete Snake episodes to execute.",
      "type": "integer",
      "const": 1500,
      "default": 1500,
      "x-snakelab-unit": "episodes"
    }
```

### Ignore Const Parameter

Any field that is a const should be excluded by Fr3d when considering which parameter to have the LLM work on next.

## Multipe Of Example

```
            "closer_to_food": {
              "type": "integer",
              "default": 2,
              "minimum": 0,
              "maximum": 4,
              "multipleOf": 2
            },
```

### Sample Prompt

Please choose a value for `closer_to_food`. The value **MUST** an integer that i greater than or equal to 0, less than or equal to 4, and be divisible by 2.

## Enum Example

```
        "sequence_length": {
          "type": "integer",
          "default": 8,
          "enum": [4, 8, 16, 32],
          "x-snakelab-unit": "frames"
        },
```

### Sample Prompt

Please choose a value for `sequence_length`. The value must be one of:
- 4
- 16
- 321

## Enum Example: Single Choice

Let the LLM sort it out. Do nothing special e.g.

### Sample Prompt

Please choose a value for 'hidden_size'. The value must be one of:
- 224




