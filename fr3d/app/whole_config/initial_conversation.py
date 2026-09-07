"""Start exploration where current gold has no comparable alternative value."""

from .prompts import prompt


def first_contact():
    return prompt('first_contact')
