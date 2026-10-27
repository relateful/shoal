import ctypes.util

import pytest

from shoal.voice.receive import opus
from shoal.voice.receive.opus import OpusDecoder, OpusError, is_loaded, load_opus
from tests.support.voice import FakeOpus


def packet(value: int) -> bytes:
    """A 20 ms Opus packet whose fake decoding is `value` in every sample."""
    return bytes([0xFC, value])


def samples(pcm: bytes) -> set[int]:
    return set(memoryview(pcm).cast("h"))


def test_a_packet_decodes_to_stereo_pcm_as_long_as_it_plays() -> None:
    decoder = OpusDecoder(library=FakeOpus())
    pcm = decoder.decode(packet(7))
    assert len(pcm) == 960 * 2 * 2
    assert samples(pcm) == {7}


def test_a_lost_packet_is_rebuilt_from_the_next_or_concealed_as_long_as_the_last() -> None:
    decoder = OpusDecoder(library=FakeOpus())
    # Before anything is decoded, a lost packet is taken to be 20 ms.
    assert len(decoder.conceal()) == 960 * 4
    _ = decoder.decode(bytes([0xFD, 7]))  # code 1: two 20 ms frames
    concealed = decoder.conceal()
    assert (len(concealed), samples(concealed)) == (1920 * 4, {0})
    assert samples(decoder.conceal(packet(9))) == {109}


def test_libopus_refusals_raise_with_its_reason_and_code() -> None:
    with pytest.raises(OpusError, match="could not create a decoder: invalid argument") as created:
        _ = OpusDecoder(library=FakeOpus(create_error=-1))
    assert created.value.code == -1
    decoder = OpusDecoder(library=FakeOpus(decode_error=-4))
    with pytest.raises(OpusError, match="could not decode a packet") as decoded:
        _ = decoder.decode(packet(1))
    assert decoded.value.code == -4


def test_a_closed_decoder_frees_its_state_once_and_refuses_to_decode() -> None:
    library = FakeOpus()
    decoder = OpusDecoder(library=library)
    decoder.close()
    decoder.close()
    assert library.destroyed == [1]
    with pytest.raises(OpusError, match="closed"):
        _ = decoder.decode(packet(1))


def find_nothing(_name: str) -> None:
    return None


def test_a_missing_libopus_says_how_to_install_it(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(opus, "_library", None)
    monkeypatch.setattr(ctypes.util, "find_library", find_nothing)
    monkeypatch.setattr("sys.platform", "linux")
    assert not is_loaded()
    with pytest.raises(OpusError, match="libopus was not found"):
        _ = OpusDecoder()


def test_loading_a_library_that_is_not_libopus_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(opus, "_library", None)
    with pytest.raises(OpusError, match="could not be loaded from 'no-such-opus'"):
        load_opus("no-such-opus")
    assert not is_loaded()


@pytest.mark.skipif(ctypes.util.find_library("opus") is None, reason="libopus is not installed")
def test_the_real_libopus_decodes_discords_silence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # pragma: no cover
    monkeypatch.setattr(opus, "_library", None)
    decoder = OpusDecoder()
    assert is_loaded()
    assert samples(decoder.decode(b"\xf8\xff\xfe")) == {0}
    decoder.close()
