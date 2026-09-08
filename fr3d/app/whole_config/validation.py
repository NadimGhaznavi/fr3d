"""Local submission sanity checks; Snake Lab owns execution validity."""

from copy import deepcopy


def submission_schema(schema):
    """Keep only types, bounds and object shape from the server schema."""
    result = {key: deepcopy(schema[key]) for key in (
        'type', 'minimum', 'maximum', 'exclusiveMinimum', 'exclusiveMaximum',
        'required', 'additionalProperties',
    ) if key in schema}
    if 'properties' in schema:
        result['properties'] = {key: submission_schema(field)
                                for key, field in schema['properties'].items()}
    return result
