from pathlib import Path

from logger import get_logger

logger = get_logger(__name__)


class RealtimeSpeakerService:
    def __init__(self) -> None:
        self._model = None

    def _init_model(self) -> None:
        if self._model is not None:
            return

        from funasr import AutoModel

        self._model = AutoModel(
            model="paraformer-zh",
            vad_model="fsmn-vad",
            punc_model="ct-punc",
            spk_model="cam++",
            disable_update=True,
        )

    def diarize(self, audio_path: str) -> list[dict]:
        path = Path(audio_path)
        if not path.exists():
            raise FileNotFoundError(audio_path)

        self._init_model()
        result = self._model.generate(
            input=str(path),
            batch_size_s=300,
            return_raw_text=True,
            is_final=True,
            sentence_timestamp=True,
        )
        return _parse_diarization_result(result)


def _parse_diarization_result(result: list) -> list[dict]:
    if not result:
        return []

    top = result[0] if isinstance(result, list) else result
    sentence_info = top.get("sentence_info") if isinstance(top, dict) else None
    items = sentence_info if sentence_info else result
    segments: list[dict] = []

    for item in items:
        if not isinstance(item, dict):
            continue
        text = (item.get("text") or "").strip()
        if not text:
            continue
        segments.append(
            {
                "text": text,
                "spk": _format_speaker_label(item.get("spk", 0)),
                "start": _normalize_timestamp(item.get("start", 0)),
                "end": _normalize_timestamp(item.get("end", 0)),
            }
        )
    return segments


def _normalize_timestamp(value) -> float:
    # FunASR sentence_info 的 start/end 统一为毫秒，一律除以 1000 转为秒。
    # 不能用「> 1000 才除」的逐值判断：小于 1 秒（1000ms）的时间戳会被漏除，
    # 例如首句从 150ms 开始会被错当成 150 秒。
    return round(float(value or 0) / 1000, 2)


def _format_speaker_label(raw) -> str:
    if isinstance(raw, int):
        return f"说话人{raw + 1}"

    text = str(raw).strip()
    digits = "".join(ch for ch in text if ch.isdigit())
    if digits:
        return f"说话人{int(digits) + 1}"
    return text or "说话人"


speaker_service = RealtimeSpeakerService()
