from engines.asr_engine import ASREngine


def test_meeting_classification_uses_speaker_count_before_noise_level():
    duration, environment = ASREngine.classify_meeting_type(420, 3, 0.9)

    assert duration == "medium"
    assert environment == "multi_speaker"


def test_meeting_classification_uses_unknown_without_diarization():
    _, environment = ASREngine.classify_meeting_type(120, None, 0.8)

    assert environment == "unknown"
