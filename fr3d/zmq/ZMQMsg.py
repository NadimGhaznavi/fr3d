#    Author: Nadim-Daniel Ghaznavi
#    Copyright: (c) 2025-2026 Nadim-Daniel Ghaznavi
#    License: GPL 3.0

import json
from typing import Any

from fr3d.constants.DZMQ import DZMQF, DZMQDef as DEFDZMQ

class ZMQMsg:
    """
    Structured message for Fr3d request/reply communication.

    ZMQMsg encapsulates messages for ZeroMQ-based RPC communication.
    It handles serialization/deserialization and provides a clean API
    for creating and accessing message components.

    Internal representation uses Python objects (dict for payload).
    Serialization to JSON happens only when converting to wire format.

        # Serialize for transmission
        json_bytes = msg.to_json()

        # Deserialize from received data
        msg = ZMQMsg.from_json(json_bytes)
    """

    def __init__(
        self,
        sender: str,
        method: str,
        target: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """
        Initialize a new ZMQMsg instance.

        Args:
            sender: Identifier of the message sender
            target: Identifier of the intended message recipient
            method: RPC method or action to be performed
            payload: Message data as a dictionary (not JSON string)

        Returns:
            None
        """
        self._sender = sender
        self._target = target
        self._method = method
        self._payload = payload if payload is not None else {}

    @property
    def sender(self) -> str:
        """Get the message sender identifier."""
        return self._sender

    @sender.setter
    def sender(self, value: str) -> None:
        """Set the message sender identifier."""
        self._sender = value

    @property
    def target(self) -> str | None:
        """Get the message target identifier."""
        return self._target

    @target.setter
    def target(self, value: str | None) -> None:
        """Set the message target identifier."""
        self._target = value

    @property
    def method(self) -> str:
        """Get the RPC method name."""
        return self._method

    @method.setter
    def method(self, value: str) -> None:
        """Set the RPC method name."""
        self._method = value

    @property
    def payload(self) -> dict[str, Any]:
        """Get the message payload as a dictionary."""
        return self._payload

    @payload.setter
    def payload(self, value: dict[str, Any]) -> None:
        """Set the message payload from a dictionary."""
        self._payload = value

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ZMQMsg":
        """
        Create a ZMQMsg from a dictionary.

        Args:
            data: Dictionary containing message fields

        Returns:
            ZMQMsg instance

        Raises:
            KeyError: If required fields are missing
        """
        if not isinstance(data, dict):
            raise TypeError("Message must be a dict")
        protocol_version = data[DZMQF.PROTOCOL_VERSION]
        if type(protocol_version) is not int or protocol_version != DEFDZMQ.PROTOCOL_VERSION:
            raise ValueError(f"Unsupported ZMQ protocol version: {protocol_version}")

        payload = data.get(DZMQF.PAYLOAD, {})
        if not isinstance(payload, dict):
            raise TypeError("Payload must be a dict")

        if DZMQF.TARGET in data:
            target = data[DZMQF.TARGET]
        else:
            target = None

        for field in (DZMQF.SENDER, DZMQF.METHOD):
            if not isinstance(data[field], str) or not data[field].strip():
                raise ValueError(f"{field} must be a nonempty string")
        if target is not None and not isinstance(target, str):
            raise TypeError("Target must be a string or None")

        return cls(
            sender=data[DZMQF.SENDER],
            target=target,
            method=data[DZMQF.METHOD],
            payload=payload,
        )

    @classmethod
    def from_json(cls, json_data: bytes) -> "ZMQMsg":
        """
        Create a ZMQMsg from JSON bytes.

        Args:
            json_data: JSON-encoded message as bytes

        Returns:
            ZMQMsg instance

        Raises:
            json.JSONDecodeError: If json_data is not valid JSON
            UnicodeDecodeError: If json_data cannot be decoded as UTF-8
        """
        return cls.from_dict(json.loads(json_data.decode("utf-8")))

    def to_dict(self) -> dict[str, Any]:
        """
        Convert message to dictionary representation.

        Returns:
            Dictionary containing all message fields including version
        """
        return {
            DZMQF.SENDER: self._sender,
            DZMQF.TARGET: self._target,
            DZMQF.METHOD: self._method,
            DZMQF.PAYLOAD: self._payload,
            DZMQF.PROTOCOL_VERSION: DEFDZMQ.PROTOCOL_VERSION,
        }

    def to_json(self) -> bytes:
        """
        Convert message to JSON bytes for transmission.

        Returns:
            JSON-encoded message as UTF-8 bytes ready for ZeroMQ

        Raises:
            TypeError: If message contains non-serializable objects
        """
        return json.dumps(self.to_dict()).encode("utf-8")

    def __repr__(self) -> str:
        """
        Return string representation of message for debugging.

        Returns:
            String showing message structure
        """
        return (
            f"ZMQMsg:{self._sender}->{self._target}:{self._method}"
            f"({self._payload})"
        )

    def __str__(self) -> str:
        """
        Return human-readable string representation.

        Returns:
            Formatted string with message details
        """
        return f"ZMQMsg:{self._sender}->{self._target}:{self._method}()"
