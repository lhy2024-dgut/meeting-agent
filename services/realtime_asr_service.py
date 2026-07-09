# -*- coding: utf-8 -*-
"""实时语音识别服务 — FunASR paraformer-zh-streaming + sounddevice

流程：
  sounddevice 持续采集 → 积攒到 600ms（9 600 samples）→ 喂 FunASR generate(is_final=False)
  → 每块文字直接 += 累积到 _accumulated_text → 停止时 is_final=True 刷出尾音
  全程共享同一个 cache，不重置。

标点：流式模型加载时附带 punc_model="ct-punc"，FunASR 在句子边界自动补全标点。

说话人识别：录音结束后调用 run_diarization(audio_path)，使用独立的离线管道
  （paraformer-zh + fsmn-vad + ct-punc + cam++），返回带 spk 标签的分句列表。
"""

import threading
import time
import wave
from pathlib import Path
from typing import Optional

import numpy as np

import config
from logger import get_logger

logger = get_logger(__name__)

# 短名 → ModelScope 缓存子目录（iic/xxx）的映射表
_MODEL_ALIASES: dict[str, str] = {
    "iic/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-online":
        "iic/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-online",
    "paraformer-zh-streaming":
        "iic/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-online",
    "ct-punc":
        "iic/punc_ct-transformer_cn-en-common-vocab471067-large",
    "fsmn-vad":
        "iic/speech_fsmn_vad_zh-cn-16k-common-pytorch",
    "cam++":
        "iic/speech_campplus_sv_zh-cn_16k-common",
    "paraformer-zh":
        "iic/speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
}


def _local_model(name: str) -> str:
    """若本地缓存存在则返回绝对路径，否则原样返回 name（触发在线下载）。"""
    subdir = _MODEL_ALIASES.get(name, name)
    local = config.FUNASR_MODEL_DIR / subdir
    if local.exists():
        logger.debug("使用本地模型: %s", local)
        return str(local)
    logger.warning("本地未找到模型 %s（路径: %s），将尝试在线下载", name, local)
    return name


SAMPLE_RATE = 16000        # Hz，FunASR 要求 16 kHz
SD_BLOCK_SAMPLES = 1024    # sounddevice 回调粒度（约 64ms）
CHUNK_STRIDE = 10 * 960    # 9 600 samples = 600ms，paraformer-zh-streaming 标准步长
CHUNK_SIZE = [0, 10, 5]    # encoder 流式配置（对应 600ms + 300ms lookahead）
ENCODER_LOOK_BACK = 4
DECODER_LOOK_BACK = 1


class RealtimeASRService:
    """sounddevice 采集 → FunASR paraformer-zh-streaming 流式转写（含标点）。"""

    def __init__(self):
        self._asr_model = None          # 流式转写模型（不含标点）
        self._punc_model = None         # 独立标点模型（ct-punc），stop 后一次性调用
        self._spk_model = None          # 离线说话人识别模型（cam++），懒加载
        self._running = False
        self._error: Optional[str] = None   # 后台线程异常消息；None 表示正常
        self._lock = threading.Lock()
        self._accumulated_text: str = ""
        self._audio_buffer: list[np.ndarray] = []
        self._record_thread: Optional[threading.Thread] = None
        self._total_samples: int = 0
        self._summary_checkpoint: int = 0   # 已提交阶段纪要的字符位置

    # ── 流式 ASR 模型加载 ─────────────────────────────────────────────────────

    def _init_asr(self):
        if self._asr_model is not None:
            return
        from funasr import AutoModel
        model_path = _local_model("iic/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-online")
        logger.info("加载 FunASR paraformer-zh-streaming: %s", model_path)
        try:
            self._asr_model = AutoModel(model=model_path, disable_update=True)
            logger.info("FunASR 流式 ASR 加载完成")
        except Exception as exc:
            raise RuntimeError(f"FunASR 加载失败: {exc}") from exc

    def _init_punc_model(self):
        if self._punc_model is not None:
            return
        from funasr import AutoModel
        model_path = _local_model("ct-punc")
        logger.info("加载 ct-punc 标点模型: %s", model_path)
        try:
            self._punc_model = AutoModel(model=model_path, disable_update=True)
            logger.info("ct-punc 加载完成")
        except Exception as exc:
            logger.warning("ct-punc 加载失败，将跳过标点恢复: %s", exc)

    def initialize(self):
        """预加载流式 ASR 模型。"""
        self._init_asr()

    # ── 离线说话人识别模型加载 ────────────────────────────────────────────────

    def _init_spk_model(self):
        if self._spk_model is not None:
            return
        from funasr import AutoModel
        logger.info("加载 FunASR 离线说话人识别管道...")
        try:
            self._spk_model = AutoModel(
                model=_local_model("paraformer-zh"),
                vad_model=_local_model("fsmn-vad"),
                punc_model=_local_model("ct-punc"),
                spk_model=_local_model("cam++"),
                disable_update=True,
            )
            logger.info("说话人识别模型加载完成")
        except Exception as exc:
            raise RuntimeError(f"说话人识别模型加载失败: {exc}") from exc

    def _apply_punctuation(self):
        """对 _accumulated_text 做一次性标点恢复（stop 后调用，不影响流式显示）。"""
        with self._lock:
            text = self._accumulated_text
        if not text.strip():
            return
        try:
            self._init_punc_model()
            if self._punc_model is None:
                return
            res = self._punc_model.generate(input=text)
            if res and res[0].get("text"):
                with self._lock:
                    self._accumulated_text = res[0]["text"].strip()
                logger.info("标点恢复完成，%d → %d 字", len(text), len(self._accumulated_text))
        except Exception as exc:
            logger.warning("标点恢复失败，保留原文: %s", exc)

    # ── 录音生命周期 ──────────────────────────────────────────────────────────

    def start(self):
        if self._running:
            return
        self._error = None
        self._running = True
        self._accumulated_text = ""
        self._audio_buffer = []
        self._total_samples = 0
        self._summary_checkpoint = 0
        self._record_thread = threading.Thread(
            target=self._recording_loop,
            daemon=True,
            name="realtime-asr",
        )
        self._record_thread.start()
        logger.info("实时 ASR 录音已开始")

    def stop(self) -> str:
        """停止录音，等待线程结束，对完整文字补全标点，返回录音 WAV 路径。"""
        if not self._running and not self._audio_buffer:
            return ""
        self._running = False
        if self._record_thread and self._record_thread.is_alive():
            self._record_thread.join(timeout=20)
        # 录音线程已结束，文字完整，一次性加标点
        self._apply_punctuation()
        return self._save_audio()

    # ── 状态读取（供 UI 轮询）────────────────────────────────────────────────

    def get_text(self) -> str:
        with self._lock:
            return self._accumulated_text

    def get_duration(self) -> float:
        return self._total_samples / SAMPLE_RATE

    def is_running(self) -> bool:
        return self._running

    def get_error(self) -> Optional[str]:
        """返回后台录音线程的异常消息；None 表示无异常。"""
        return self._error

    def get_text_window(self) -> tuple[str, int]:
        """返回自上次阶段纪要 checkpoint 以来的新增文本和当前总长度。

        线程安全；UI 层在触发摘要任务后应调用 advance_checkpoint(new_pos)。
        """
        with self._lock:
            text = self._accumulated_text
            pos = min(self._summary_checkpoint, len(text))
            return text[pos:], len(text)

    def advance_checkpoint(self, pos: int):
        """将阶段纪要 checkpoint 推进到 pos，避免下次重复送入已摘要的文本。"""
        with self._lock:
            self._summary_checkpoint = pos

    # ── 说话人识别（离线，录音结束后调用）───────────────────────────────────

    def run_diarization(self, audio_path: str) -> list[dict]:
        """对保存的 WAV 文件运行离线说话人识别。

        Returns:
            list of {"text": str, "spk": str, "start": float, "end": float}
            时间单位：秒。若失败返回空列表。
        """
        if not audio_path or not Path(audio_path).exists():
            logger.warning("run_diarization: 音频文件不存在 %s", audio_path)
            return []

        self._init_spk_model()

        try:
            res = self._spk_model.generate(
                input=audio_path,
                batch_size_s=300,
                return_raw_text=True,
                is_final=True,
                sentence_timestamp=True,
            )
        except Exception as exc:
            logger.error("说话人识别推理失败: %s", exc, exc_info=True)
            return []

        return _parse_diarization_result(res)

    # ── 核心录音 + 推理循环 ───────────────────────────────────────────────────

    def _recording_loop(self):
        try:
            import sounddevice as sd
        except ImportError as exc:
            self._error = "sounddevice 未安装，请执行: pip install sounddevice"
            self._running = False
            logger.error("sounddevice 未安装: %s", exc)
            return

        audio_queue: list[np.ndarray] = []
        q_lock = threading.Lock()

        def sd_callback(indata, frames, time_info, status):
            if status:
                logger.debug("sounddevice: %s", status)
            if self._running:
                chunk = indata[:, 0].astype(np.float32).copy()
                with q_lock:
                    audio_queue.append(chunk)
                self._audio_buffer.append(chunk)

        cache: dict = {}                     # 全程共享，绝不重置
        acc: list[np.ndarray] = []           # 未凑满 CHUNK_STRIDE 的零头

        try:
            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
                blocksize=SD_BLOCK_SAMPLES,
                callback=sd_callback,
            ):
                logger.info("麦克风已打开 (%d Hz)", SAMPLE_RATE)
                while self._running:
                    with q_lock:
                        pending = audio_queue[:]
                        audio_queue.clear()

                    for raw in pending:
                        acc.append(raw)
                        self._total_samples += len(raw)

                    acc_arr = np.concatenate(acc) if acc else np.array([], dtype=np.float32)
                    while len(acc_arr) >= CHUNK_STRIDE:
                        chunk = acc_arr[:CHUNK_STRIDE]
                        acc_arr = acc_arr[CHUNK_STRIDE:]
                        text = self._infer(chunk, cache, is_final=False)
                        if text:
                            with self._lock:
                                self._accumulated_text += text

                    acc = [acc_arr] if len(acc_arr) > 0 else []
                    time.sleep(0.02)

        except Exception as exc:
            self._error = str(exc)
            logger.error("录音循环异常: %s", exc, exc_info=True)
        finally:
            self._running = False   # 线程退出时始终重置，防止 UI 显示假状态
            remaining = np.concatenate(acc) if acc else np.array([], dtype=np.float32)
            if len(remaining) > SAMPLE_RATE * 0.1:
                try:
                    text = self._infer(remaining, cache, is_final=True)
                    if text:
                        with self._lock:
                            self._accumulated_text += text
                except Exception:
                    pass
            duration = self._total_samples / SAMPLE_RATE
            logger.info("录音结束，时长 %.1fs，识别 %d 字", duration, len(self._accumulated_text))

    # ── FunASR 推理 ───────────────────────────────────────────────────────────

    def _infer(self, chunk: np.ndarray, cache: dict, is_final: bool) -> str:
        try:
            res = self._asr_model.generate(
                input=chunk,
                cache=cache,
                language="zh",
                use_itn=True,
                is_final=is_final,
                chunk_size=CHUNK_SIZE,
                encoder_chunk_look_back=ENCODER_LOOK_BACK,
                decoder_chunk_look_back=DECODER_LOOK_BACK,
            )
            if res and res[0].get("text"):
                return res[0]["text"].strip()
        except Exception as exc:
            logger.debug("FunASR %s: %s", "final" if is_final else "chunk", exc)
        return ""

    # ── 音频保存 ──────────────────────────────────────────────────────────────

    def _save_audio(self) -> str:
        if not self._audio_buffer:
            return ""
        try:
            audio = np.concatenate(self._audio_buffer)
            i16 = np.clip(audio * 32767, -32768, 32767).astype(np.int16)
            out = Path(config.AUDIO_DIR) / f"realtime_{int(time.time())}.wav"
            with wave.open(str(out), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(SAMPLE_RATE)
                wf.writeframes(i16.tobytes())
            logger.info("录音保存: %s (%.1fs)", out, len(audio) / SAMPLE_RATE)
            return str(out)
        except Exception as exc:
            logger.error("保存录音失败: %s", exc)
            return ""


# ── 说话人识别结果解析 ────────────────────────────────────────────────────────

def _parse_diarization_result(res: list) -> list[dict]:
    """解析 FunASR 离线说话人识别输出，统一为 {"text", "spk", "start", "end"} 列表。

    FunASR 的输出格式在不同版本/配置下略有差异，这里做兼容处理：
    - sentence_info 格式：res[0]['sentence_info'] = [{"text","spk","start","end"}, ...]
    - 顶层列表格式：res 直接是 [{"text","spk","start","end"}, ...]
    时间单位由毫秒统一转换为秒。
    """
    if not res:
        return []

    segments = []

    def ms_to_s(val):
        """FunASR 时间戳可能是毫秒整数，也可能已是秒浮点数，统一转为秒。"""
        if isinstance(val, (int, float)) and val > 1000:
            return round(val / 1000, 2)
        return round(float(val), 2)

    def spk_label(raw_spk) -> str:
        if isinstance(raw_spk, int):
            return f"说话人{raw_spk + 1}"
        s = str(raw_spk).strip()
        # "spk0" / "spk_0" → "说话人1"
        import re
        m = re.search(r"(\d+)$", s)
        if m:
            return f"说话人{int(m.group(1)) + 1}"
        return s or "说话人1"

    # 优先读 sentence_info 字段
    top = res[0] if isinstance(res, list) and res else res
    sentence_info = None
    if isinstance(top, dict):
        sentence_info = top.get("sentence_info")

    if sentence_info:
        for item in sentence_info:
            text = (item.get("text") or "").strip()
            if not text:
                continue
            segments.append({
                "text": text,
                "spk": spk_label(item.get("spk", 0)),
                "start": ms_to_s(item.get("start", 0)),
                "end": ms_to_s(item.get("end", 0)),
            })
        return segments

    # 兜底：顶层 list 逐条解析
    source = res if isinstance(res, list) else [res]
    for item in source:
        if not isinstance(item, dict):
            continue
        text = (item.get("text") or "").strip()
        if not text:
            continue
        segments.append({
            "text": text,
            "spk": spk_label(item.get("spk", 0)),
            "start": ms_to_s(item.get("start", 0)),
            "end": ms_to_s(item.get("end", 0)),
        })

    # 如果连 spk 字段都没有，说明模型没有返回说话人信息
    if segments and all(s["spk"] == "说话人1" for s in segments):
        logger.warning("说话人识别结果中无 spk 字段，可能模型未成功分离说话人")

    return segments


# ── 单例 ─────────────────────────────────────────────────────────────────────

_instance: Optional[RealtimeASRService] = None
_instance_lock = threading.Lock()


def get_realtime_service() -> RealtimeASRService:
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = RealtimeASRService()
    return _instance
