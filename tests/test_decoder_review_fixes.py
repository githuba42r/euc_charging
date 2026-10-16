"""Decoder hooks added in the review fix wave."""

from euc_charging.decoders import (
    GotwayDecoder,
    InMotionDecoder,
    InMotionV2Decoder,
    KingSongDecoder,
    NinebotDecoder,
    NinebotZDecoder,
    VeteranDecoder,
)


def test_split_write_matches_euc_world_buffer_reuse():
    """ui/a.java (fallback): 20-byte pieces, remainder in the reused buffer."""
    d = InMotionDecoder()
    packet = bytes(range(45))
    assert d.split_write(packet) == [packet[:20], packet[20:40], packet[40:45] + packet[25:40]]
    assert d.split_write(packet[:20]) == [packet[:20]]
    assert NinebotDecoder().split_write(packet) == [packet]


def test_has_pending_requests():
    gw = GotwayDecoder()
    assert gw.has_pending_requests
    gw._probe = "done"
    assert not gw.has_pending_requests
    ks = KingSongDecoder()
    assert ks.has_pending_requests
    ks._name_answered = True
    assert not ks.has_pending_requests
    for cls in (NinebotDecoder, NinebotZDecoder, InMotionDecoder, InMotionV2Decoder):
        assert cls().has_pending_requests
    assert not VeteranDecoder().has_pending_requests


def test_gotway_name_reply_strips_line_ending():
    d = GotwayDecoder()
    d.decode(b"NAME:Master Pro\r\n")
    assert d.wheel_name == "Master Pro"
