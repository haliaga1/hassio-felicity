"""Unit tests for the WebSocket frame parsing and the reconnect policy."""

from __future__ import annotations

import json

import pytest
from helpers import load_fixture

from felicity_client.models.common import ProductType
from felicity_client.realtime import (
    RealtimeService,
    SubscriptionCommand,
    parse_snapshot_frame,
)


class TestSubscriptionCommand:
    def test_renders_the_device_command(self) -> None:
        payload = SubscriptionCommand(device_sn="INV0001", collector_sn="COL0001").to_payload()
        assert payload == {
            "type": "command",
            "plant": False,
            "deviceCommand": {"deviceSn": "INV0001", "collectorSn": "COL0001"},
        }

    def test_renders_the_plant_command(self) -> None:
        payload = SubscriptionCommand(device_sn="plant-0001").to_payload(plant=True)
        assert payload == {"type": "command", "plant": True}

    def test_is_json_serialisable(self) -> None:
        payload = SubscriptionCommand(device_sn="INV0001").to_payload()
        assert json.loads(json.dumps(payload)) == payload


class TestParseSnapshotFrame:
    def test_parses_the_real_time_data_envelope(self) -> None:
        snapshot = load_fixture("snapshot_inverter.json")
        frame = json.dumps({"realTimeData": {"deviceSnapshot": snapshot}})
        parsed = parse_snapshot_frame(frame)
        assert parsed is not None
        assert parsed.device_sn == snapshot["deviceSn"]
        assert parsed.product_type is ProductType.INVERTER
        assert parsed.pv.power == pytest.approx(float(snapshot["pvTotalPower"]))

    def test_parses_a_bare_device_snapshot(self) -> None:
        snapshot = load_fixture("snapshot_battery.json")
        parsed = parse_snapshot_frame(json.dumps({"deviceSnapshot": snapshot}))
        assert parsed is not None
        assert parsed.device_sn == snapshot["deviceSn"]

    def test_parses_a_top_level_snapshot(self) -> None:
        snapshot = load_fixture("snapshot_controller.json")
        parsed = parse_snapshot_frame(json.dumps(snapshot))
        assert parsed is not None
        assert parsed.device_sn == snapshot["deviceSn"]

    def test_accepts_bytes(self) -> None:
        snapshot = load_fixture("snapshot_inverter.json")
        frame = json.dumps({"realTimeData": {"deviceSnapshot": snapshot}}).encode()
        assert parse_snapshot_frame(frame) is not None

    @pytest.mark.parametrize(
        "frame",
        [
            "",
            "not json",
            "[1, 2, 3]",
            '"a string"',
            "{}",
            '{"type":"ack"}',
            '{"realTimeData":{}}',
        ],
    )
    def test_ignores_frames_without_a_snapshot(self, frame: str) -> None:
        assert parse_snapshot_frame(frame) is None

    def test_ignores_invalid_utf8(self) -> None:
        assert parse_snapshot_frame(b"\xff\xfe\x00") is None


class TestBackoff:
    def test_grows_and_is_bounded(self) -> None:
        service = RealtimeService("wss://example.test")
        delays = [service._backoff_delay(attempt) for attempt in range(1, 12)]
        # The jitter makes the values vary slightly, so compare the ranges.
        assert delays[0] < delays[3] < delays[8]
        assert max(delays) <= 60.0 * 1.25

    def test_starts_small(self) -> None:
        service = RealtimeService("wss://example.test")
        assert service._backoff_delay(1) < 2.0

    def test_connection_count_starts_at_zero(self) -> None:
        service = RealtimeService("wss://example.test")
        assert service.connection_count == 0
        assert service.is_connected is False


class TestHandshakeHeaders:
    async def test_without_a_token_provider_there_are_no_headers(self) -> None:
        service = RealtimeService("wss://example.test")
        assert await service._handshake_headers() == {}

    async def test_sends_the_bearer_token(self) -> None:
        async def _token() -> str:
            return "Bearer_abc"

        service = RealtimeService("wss://example.test", token_provider=_token)
        assert await service._handshake_headers() == {"Authorization": "Bearer_abc"}

    async def test_survives_a_token_failure(self) -> None:
        async def _token() -> str:
            raise RuntimeError("no token")

        service = RealtimeService("wss://example.test", token_provider=_token)
        assert await service._handshake_headers() == {}
