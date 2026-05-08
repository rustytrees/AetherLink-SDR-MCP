"""
ACARS message file parsing for acarsdec subprocess output.
"""

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


ACARS_DEFAULT_FREQUENCIES_MHZ = [131.550, 131.525, 131.725, 130.025, 130.450]


@dataclass
class ACARSMessage:
    """Decoded ACARS message summary."""

    timestamp: str
    label: Optional[str] = None
    mode: Optional[str] = None
    aircraft: Optional[str] = None
    flight: Optional[str] = None
    frequency_mhz: Optional[float] = None
    text: str = ""
    raw: Optional[Dict[str, Any]] = None


class ACARSDecoder:
    """Tracks and parses acarsdec output files."""

    def __init__(self):
        self.output_dir: Optional[str] = None
        self.frequencies_mhz: List[float] = list(ACARS_DEFAULT_FREQUENCIES_MHZ)
        self.gain: float = 40
        self.messages: List[ACARSMessage] = []
        self.last_refresh: Optional[datetime] = None

    def start_session(
        self,
        output_dir: str,
        frequencies_mhz: List[float],
        gain: float,
    ) -> None:
        """Initialize a new ACARS output session."""
        self.output_dir = output_dir
        self.frequencies_mhz = frequencies_mhz
        self.gain = gain
        self.messages = []
        self.last_refresh = None

    def refresh(self) -> List[Dict[str, Any]]:
        """Read ACARS messages from the current output directory."""
        if not self.output_dir:
            return []

        output_path = Path(self.output_dir)
        json_path = output_path / "messages.json"
        oneline_path = output_path / "oneline.txt"

        messages = self._read_json_messages(json_path)
        if not messages:
            messages = self._read_oneline_messages(oneline_path)

        self.messages = messages
        self.last_refresh = datetime.now()
        return self.get_messages()

    def get_messages(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Return parsed messages as dictionaries."""
        messages = self.messages[-limit:] if limit else self.messages
        return [asdict(message) for message in messages]

    def get_statistics(self) -> Dict[str, Any]:
        """Return ACARS session statistics."""
        aircraft_seen = {
            message.aircraft for message in self.messages if message.aircraft
        }
        flights_seen = {
            message.flight for message in self.messages if message.flight
        }
        return {
            "total_messages": len(self.messages),
            "aircraft_seen": len(aircraft_seen),
            "flights_seen": len(flights_seen),
            "output_dir": self.output_dir,
            "frequencies_mhz": self.frequencies_mhz,
            "gain": self.gain,
            "last_refresh": self.last_refresh.isoformat() if self.last_refresh else None,
        }

    def _read_json_messages(self, path: Path) -> List[ACARSMessage]:
        if not path.exists():
            return []

        messages = []
        for line in path.read_text(errors="replace").splitlines():
            line = line.strip().rstrip(",")
            if not line or line in ("[", "]"):
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                messages.append(self._message_from_json(payload))

        return messages

    def _read_oneline_messages(self, path: Path) -> List[ACARSMessage]:
        if not path.exists():
            return []

        messages = []
        for line in path.read_text(errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            messages.append(ACARSMessage(
                timestamp=datetime.now().isoformat(),
                text=line,
                raw={"line": line},
            ))
        return messages

    def _message_from_json(self, payload: Dict[str, Any]) -> ACARSMessage:
        frequency = self._first(payload, "freq", "frequency", "frequency_mhz", "channel")
        frequency_mhz = self._parse_frequency_mhz(frequency)
        timestamp = self._first(payload, "timestamp", "time", "datetime", "date")
        text = self._first(
            payload,
            "text",
            "message",
            "msg_text",
            "content",
            "block",
        )

        return ACARSMessage(
            timestamp=str(timestamp or datetime.now().isoformat()),
            label=self._string_or_none(self._first(payload, "label", "lbl")),
            mode=self._string_or_none(self._first(payload, "mode")),
            aircraft=self._string_or_none(self._first(
                payload, "aircraft", "aircraft_reg", "tail", "tail_number", "reg"
            )),
            flight=self._string_or_none(self._first(payload, "flight", "flight_id", "fid")),
            frequency_mhz=frequency_mhz,
            text=str(text or ""),
            raw=payload,
        )

    def _parse_frequency_mhz(self, value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            frequency = float(value)
        except (TypeError, ValueError):
            return None
        return frequency / 1e6 if frequency > 1000 else frequency

    def _first(self, payload: Dict[str, Any], *keys: str) -> Any:
        for key in keys:
            if key in payload and payload[key] not in (None, ""):
                return payload[key]
        return None

    def _string_or_none(self, value: Any) -> Optional[str]:
        return str(value) if value not in (None, "") else None
