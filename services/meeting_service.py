import json
import re
import time
from pathlib import Path

import yaml

from chains.export_chain import ExportChain
from chains.minutes_chain import (
    MinutesChain,
    PLACEHOLDER_NO_ACTION,
    PLACEHOLDER_NO_RESOLUTION,
    normalize_structured_minutes_output,
)
from engines.asr_engine import (
    ASREngine,
    _PARALLEL_MIN_SEC,
    _get_audio_duration,
    get_asr_engine,
)
from engines.llm import get_llm
from logger import get_logger
from rag.retriever import get_retriever
from services.terms_service import save_terms

logger = get_logger(__name__)

_FALLBACK_TRANSCRIPT_LEN = 4000

ASR_MODEL_WHISPER = "faster-whisper"
ASR_MODEL_SENSEVOICE = "SenseVoiceSmall"


class MeetingService:
    """会议处理完整流程，所有依赖通过构造函数注入。"""

    def __init__(self, db_repo, asr_engine=None, minutes_chain=None, export_chain=None):
        self.db = db_repo
        self._asr = asr_engine
        self._sv_engine = None
        self.minutes_chain = minutes_chain or MinutesChain()
        self.export_chain = export_chain or ExportChain()

    @property
    def asr(self):
        if self._asr is None:
            self._asr = get_asr_engine()
        return self._asr

    def _get_engine(self, asr_model: str):
        """根据 asr_model 名称返回对应引擎单例。"""
        if asr_model == ASR_MODEL_SENSEVOICE:
            if self._sv_engine is None:
                from engines.sense_voice_engine import get_sensevoice_engine

                self._sv_engine = get_sensevoice_engine()
            return self._sv_engine
        return self.asr

    def process(
        self,
        file_path,
        file_hash,
        title,
        meeting_dt,
        user_id=None,
        output_format="docx",
        template_path=None,
        progress_callback=None,
        scene="通用会议",
        custom_headings=None,
        asr_model=ASR_MODEL_WHISPER,
        terms=None,
        chunk_strategy=None,
        is_private=False,
    ):
        """批量处理：ASR -> 分类 -> LLM -> 持久化 -> RAG -> 导出。"""
        cached = self.db.get_meeting_by_hash(file_hash, user_id=user_id)
        if not terms and cached and any(
            [cached.minutes_text, cached.action_items_text, cached.resolutions_text]
        ):
            return self._handle_cache_hit(cached, output_format, template_path, progress_callback)

        engine = self._get_engine(asr_model)
        if progress_callback:
            progress_callback(10, "🎤 语音识别中...")
        segments, _ = engine.transcribe(file_path, terms=terms)
        transcript = " ".join(seg.get("text", "") for seg in segments)

        return self._finalize(
            segments,
            transcript,
            file_path,
            file_hash,
            title,
            meeting_dt,
            output_format,
            template_path,
            progress_callback,
            scene=scene,
            custom_headings=custom_headings,
            terms=terms,
            chunk_strategy=chunk_strategy,
            asr_model=asr_model,
            user_id=user_id,
            diarize_audio=True,
            is_private=is_private,
        )

    def process_stream(
        self,
        file_path,
        file_hash,
        title,
        meeting_dt,
        user_id=None,
        output_format="docx",
        template_path=None,
        progress_callback=None,
        scene="通用会议",
        custom_headings=None,
        asr_model=ASR_MODEL_WHISPER,
        terms=None,
        chunk_strategy=None,
        transcription_mode="auto",
        is_private=False,
    ):
        """流式处理：边转写边返回结果。"""
        engine = self._get_engine(asr_model)
        asr_start = time.time()

        duration_s = _get_audio_duration(file_path)
        if transcription_mode == "parallel":
            use_parallel = True
        elif transcription_mode == "direct":
            use_parallel = False
        else:
            use_parallel = duration_s >= _PARALLEL_MIN_SEC

        if use_parallel:
            segments = []
            for event in engine.transcribe_parallel_iter(file_path, terms=terms):
                if event["type"] == "chunk_done":
                    elapsed = time.time() - asr_start
                    msg = (
                        f"🎤 [{asr_model}] 并行转写... [{event['completed']}/{event['total']} 片段完成]"
                        f"  ⏱ {elapsed:.0f}s"
                    )
                    if progress_callback:
                        progress_callback(event["pct"], msg)
                    yield {
                        "type": "parallel_progress",
                        "pct": event["pct"],
                        "msg": msg,
                        "completed": event["completed"],
                        "total": event["total"],
                    }
                elif event["type"] == "complete":
                    segments = event["segments"]
            transcript = " ".join(seg.get("text", "") for seg in segments)
        else:
            progress = {"pct": 0, "msg": "", "segments": [], "transcript_parts": []}
            for item, duration in engine.transcribe_iter(file_path, terms=terms):
                progress["segments"].append(item)
                progress["transcript_parts"].append(item.get("text", ""))
                elapsed = time.time() - asr_start
                progress["pct"] = min(55, int(item["end"] / max(duration, 1) * 55))
                progress["msg"] = (
                    f"🎤 [{asr_model}] 转写... [{item['end']:.0f}s / {duration:.0f}s]"
                    f"  ⏱ {elapsed:.0f}s"
                )
                if progress_callback:
                    progress_callback(progress["pct"], progress["msg"])
                yield {"type": "segment", "segment": item, "progress": dict(progress)}
            transcript = " ".join(progress["transcript_parts"])
            segments = progress["segments"]

        asr_time = time.time() - asr_start

        final = self._finalize(
            segments,
            transcript,
            file_path,
            file_hash,
            title,
            meeting_dt,
            output_format,
            template_path,
            progress_callback,
            scene=scene,
            custom_headings=custom_headings,
            terms=terms,
            chunk_strategy=chunk_strategy,
            asr_model=asr_model,
            user_id=user_id,
            diarize_audio=True,
            is_private=is_private,
        )
        final["asr_time"] = asr_time
        yield {"type": "complete", "data": final}

        if progress_callback:
            progress_callback(100, "OK 完成")

    def export(self, data, output_format="docx", template_path=None):
        return self.export_chain.run(data, output_format, template_path)

    def process_from_realtime(
        self,
        segments,
        audio_path,
        file_hash,
        title,
        meeting_dt,
        user_id=None,
        output_format="docx",
        template_path=None,
        progress_callback=None,
        scene="通用会议",
        custom_headings=None,
        terms=None,
        chunk_strategy=None,
        is_private=False,
    ):
        """使用实时录音阶段已经累计好的转写结果生成会议纪要。"""
        transcript = " ".join(seg.get("text", "") for seg in segments)
        return self._finalize(
            segments,
            transcript,
            audio_path,
            file_hash,
            title,
            meeting_dt,
            output_format,
            template_path,
            progress_callback,
            scene=scene,
            custom_headings=custom_headings,
            terms=terms,
            chunk_strategy=chunk_strategy,
            asr_model="realtime-browser",
            user_id=user_id,
            is_private=is_private,
        )

    def _handle_cache_hit(self, cached, output_format, template_path, progress_callback):
        segments = [
            {
                "start": item.start_time,
                "end": item.end_time,
                "text": item.text,
                "duration": (item.end_time or 0) - (item.start_time or 0),
            }
            for item in cached.transcriptions
        ]
        transcript = " ".join(seg["text"] for seg in segments)
        output_data = {
            "meeting_id": cached.id,
            "title": cached.title,
            "date": cached.created_at.strftime("%Y-%m-%d %H:%M"),
            "minutes": cached.minutes_text or "",
            "action_items": cached.action_items_text or "",
            "resolutions": cached.resolutions_text or "",
        }
        normalized_action_items, normalized_resolutions, normalized_minutes, _ = (
            normalize_structured_minutes_output(
                output_data["minutes"],
                output_data["action_items"],
                output_data["resolutions"],
                title=cached.title or "",
                date=output_data["date"],
            )
        )
        output_data["minutes"] = normalized_minutes
        output_data["action_items"] = normalized_action_items
        output_data["resolutions"] = normalized_resolutions
        output_path = self.export_chain.run(output_data, output_format, template_path)
        if progress_callback:
            progress_callback(100, "⚡ 缓存命中")
        return {
            "transcript": transcript,
            "segments": segments,
            "minutes": output_data["minutes"],
            "action_items": output_data["action_items"],
            "resolutions": output_data["resolutions"],
            "short_summary": cached.short_summary or "",
            "project_name": cached.project_name or "",
            "meeting_id": cached.id,
            "title": cached.title,
            "output_path": output_path,
            "duration_category": cached.duration_category,
            "environment": cached.environment,
        }

    def _finalize(
        self,
        segments,
        transcript,
        file_path,
        file_hash,
        title,
        meeting_dt,
        output_format="docx",
        template_path=None,
        progress_callback=None,
        scene="通用会议",
        custom_headings=None,
        terms=None,
        chunk_strategy=None,
        asr_model=None,
        user_id=None,
        diarize_audio=False,
        is_private=False,
    ):
        """Steps 3-7: 分类 -> (说话人识别) -> LLM 提取 -> 持久化 -> RAG 索引 -> 导出。

        diarize_audio=True 时（上传/普通处理），在保存前对原始音频运行离线说话人
        识别，用带说话人标签的分句替换落库/展示用的 segments；会议纪要仍使用传入的
        ASR transcript，不受影响。实时流程传入的 segments 已含 speaker，无需重复识别。
        """
        if progress_callback:
            progress_callback(55, "📊 分析会议特征...")
        duration = max((seg.get("end", 0) for seg in segments), default=0)
        duration_category, environment = self._classify_without_diarization(duration)
        meeting_id = self.db.create_meeting(
            title,
            file_path,
            duration_category,
            environment,
            file_hash,
            user_id=user_id,
            created_at=meeting_dt,
            is_private=is_private,
        )

        if terms:
            try:
                save_terms(meeting_id, terms)
            except Exception as exc:
                logger.warning("保存术语词表失败: %s", exc)

        if progress_callback:
            progress_callback(65, "🤖 生成会议纪要...")
        date_str = meeting_dt.strftime("%Y-%m-%d %H:%M")
        action_items, resolutions, minutes = self.minutes_chain.run(
            transcript,
            title=title,
            date=date_str,
            scene=scene,
            custom_headings=custom_headings,
        )
        action_items, resolutions, minutes, normalized = normalize_structured_minutes_output(
            minutes,
            action_items,
            resolutions,
            title=title,
            date=date_str,
        )
        if normalized:
            logger.info("已在保存前修复结构化纪要 JSON: title=%s", title)

        if not (minutes or "").strip():
            if len(transcript or "") > _FALLBACK_TRANSCRIPT_LEN:
                logger.warning(
                    "纪要生成返回空，回退原文截断 (%d -> %d 字符)",
                    len(transcript),
                    _FALLBACK_TRANSCRIPT_LEN,
                )
            minutes = (
                f"# 会议纪要：{title}\n\n**日期**：{date_str}\n\n"
                f"## 转录文本\n{(transcript or '无')[:_FALLBACK_TRANSCRIPT_LEN]}"
            )
        if not (action_items or "").strip():
            action_items = PLACEHOLDER_NO_ACTION
        if not (resolutions or "").strip():
            resolutions = PLACEHOLDER_NO_RESOLUTION

        if progress_callback:
            progress_callback(72, "📝 生成摘要...")
        short_summary, project_name = self._generate_summary(transcript, minutes)

        stored_segments = segments
        if diarize_audio and file_path:
            if progress_callback:
                progress_callback(78, "🗣️ 识别说话人...")
            stored_segments = self._diarize_segments(file_path, fallback=segments)

        if progress_callback:
            progress_callback(80, "💾 保存结果...")
        self.db.add_transcriptions_bulk(meeting_id, stored_segments, user_id=user_id)
        self.db.update_meeting_results(
            meeting_id,
            minutes,
            action_items,
            resolutions,
            short_summary=short_summary,
            project_name=project_name,
            user_id=user_id,
        )

        if progress_callback:
            progress_callback(88, "🔍 索引到知识库...")
        try:
            get_retriever().rebuild_meeting_index(
                meeting_id,
                transcript=transcript,
                minutes=minutes,
                action_items=action_items,
                resolutions=resolutions,
                chunk_strategy=chunk_strategy,
                segments=segments,
                asr_model=asr_model or ASR_MODEL_WHISPER,
            )
        except Exception as exc:
            logger.warning("RAG 索引重建失败，已保留旧索引: %s", exc)

        if progress_callback:
            progress_callback(95, "📄 导出文档...")
        output_data = {
            "meeting_id": meeting_id,
            "title": title,
            "date": date_str,
            "minutes": minutes,
            "action_items": action_items,
            "resolutions": resolutions,
        }
        output_path = self.export_chain.run(output_data, output_format, template_path)

        if progress_callback:
            progress_callback(100, "OK 完成")

        return {
            "transcript": transcript,
            "segments": segments,
            "minutes": minutes,
            "action_items": action_items,
            "resolutions": resolutions,
            "short_summary": short_summary,
            "project_name": project_name,
            "meeting_id": meeting_id,
            "title": title,
            "output_path": output_path,
            "duration_category": duration_category,
            "environment": environment,
        }

    @staticmethod
    def _diarize_segments(audio_path, fallback):
        """对原始音频运行离线说话人识别，返回带 speaker 标签的分句列表。

        复用与实时转写一致的 speaker_service（paraformer-zh + fsmn-vad + ct-punc + cam++）。
        识别失败或无结果时回退到传入的 fallback segments（不带说话人），不阻断主流程。
        """
        try:
            from services.realtime_speaker_service import speaker_service

            spk_segments = speaker_service.diarize(audio_path)
        except Exception as exc:
            logger.warning("说话人识别失败，回退无说话人转录: %s", exc)
            return fallback

        if not spk_segments:
            logger.warning("说话人识别无结果，回退无说话人转录")
            return fallback

        return [
            {
                "text": item.get("text", ""),
                "start": item.get("start", 0.0),
                "end": item.get("end", 0.0),
                "speaker": item.get("spk", ""),
            }
            for item in spk_segments
        ]

    @staticmethod
    def _generate_summary(transcript, minutes):
        """调用 LLM 生成 short_summary 和 project_name，失败时回退。"""
        try:
            template_path = (
                Path(__file__).resolve().parent.parent
                / "prompts"
                / "templates"
                / "auto_summary.yaml"
            )
            with open(template_path, "r", encoding="utf-8") as file:
                template = yaml.safe_load(file)
            system_prompt = template["system"].format(
                transcript=(transcript or "")[:3000],
                minutes=(minutes or "")[:1000],
            )
        except Exception as exc:
            logger.warning("加载 auto_summary 模板失败: %s", exc)
            return (minutes or "")[:200], "未分类"
        try:
            llm = get_llm(temperature=0.1)
            response = llm.invoke(system_prompt)
            text = response.content if hasattr(response, "content") else str(response)
        except Exception as exc:
            logger.warning("摘要 LLM 调用失败: %s", exc)
            return (minutes or "")[:200], "未分类"

        try:
            text = text.strip()
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
            data = json.loads(text)
            project_name = str(data.get("project_name", "未分类"))[:20]
            short_summary = str(data.get("short_summary", ""))[:200]
            return short_summary, project_name
        except (json.JSONDecodeError, TypeError, KeyError) as exc:
            logger.warning("摘要 JSON 解析失败: %s, raw=%s", exc, text[:100])
            return (minutes or "")[:200], "未分类"

    @staticmethod
    def _classify_without_diarization(duration: float) -> tuple[str, str]:
        """Avoid presenting ASR segment timing or audio level as environment evidence."""
        return ASREngine.classify_meeting_type(duration, num_speakers=None)

