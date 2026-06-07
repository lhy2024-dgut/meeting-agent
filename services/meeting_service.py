import json
import re
import time
from pathlib import Path

import yaml

from chains.minutes_chain import MinutesChain
from chains.export_chain import ExportChain
from engines.asr_engine import ASREngine, _get_audio_duration, _PARALLEL_MIN_SEC
from engines.llm import get_llm
from logger import get_logger
from rag.retriever import get_retriever
from services.terms_service import save_terms

logger = get_logger(__name__)

_FALLBACK_TRANSCRIPT_LEN = 4000

ASR_MODEL_WHISPER = "faster-whisper"
ASR_MODEL_SENSEVOICE = "SenseVoiceSmall"


class MeetingService:
    """会议处理完整流程，所有依赖通过构造函数注入"""

    def __init__(self, db_repo, asr_engine=None, minutes_chain=None, export_chain=None):
        self.db = db_repo
        self._asr = asr_engine
        self._sv_engine = None
        self.minutes_chain = minutes_chain or MinutesChain()
        self.export_chain = export_chain or ExportChain()

    @property
    def asr(self):
        if self._asr is None:
            self._asr = ASREngine()
        return self._asr

    def _get_engine(self, asr_model: str):
        """根据 asr_model 名称返回对应引擎实例"""
        if asr_model == ASR_MODEL_SENSEVOICE:
            if self._sv_engine is None:
                from engines.sense_voice_engine import SenseVoiceEngine
                self._sv_engine = SenseVoiceEngine()
            return self._sv_engine
        return self.asr

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process(
        self,
        file_path,
        file_hash,
        title,
        meeting_dt,
        output_format="docx",
        template_path=None,
        progress_callback=None,
        scene="通用会议",
        custom_headings=None,
        asr_model=ASR_MODEL_WHISPER,
        terms=None,
    ):
        """批量处理：ASR → 分类 → LLM → 持久化 → RAG → 导出"""
        cached = self.db.get_meeting_by_hash(file_hash)
        if cached and any(
            [cached.minutes_text, cached.action_items_text, cached.resolutions_text]
        ):
            return self._handle_cache_hit(cached, output_format, template_path, progress_callback)

        engine = self._get_engine(asr_model)
        if progress_callback:
            progress_callback(10, "🎤 语音识别中...")
        segments, _ = engine.transcribe(file_path, terms=terms)
        transcript = " ".join(seg.get("text", "") for seg in segments)

        return self._finalize(
            segments, transcript, file_path, file_hash, title, meeting_dt,
            output_format, template_path, progress_callback,
            scene=scene, custom_headings=custom_headings, terms=terms,
        )

    def process_stream(
        self,
        file_path,
        file_hash,
        title,
        meeting_dt,
        output_format="docx",
        template_path=None,
        progress_callback=None,
        scene="通用会议",
        custom_headings=None,
        asr_model=ASR_MODEL_WHISPER,
        terms=None,
    ):
        """流式处理：边转写边返回结果；长音频自动切换并行模式"""
        engine = self._get_engine(asr_model)
        asr_start = time.time()

        duration_s = _get_audio_duration(file_path)
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
                    yield {"type": "parallel_progress", "pct": event["pct"], "msg": msg,
                           "completed": event["completed"], "total": event["total"]}
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
            segments, transcript, file_path, file_hash, title, meeting_dt,
            output_format, template_path, progress_callback,
            scene=scene, custom_headings=custom_headings, terms=terms,
        )
        final["asr_time"] = asr_time
        yield {"type": "complete", "data": final}

        if progress_callback:
            progress_callback(100, "OK 完成")

    def export(self, data, output_format="docx", template_path=None):
        return self.export_chain.run(data, output_format, template_path)

    # ------------------------------------------------------------------
    # Private: shared pipeline
    # ------------------------------------------------------------------

    def _handle_cache_hit(self, cached, output_format, template_path, progress_callback):
        segments = [
            {
                "start": t.start_time,
                "end": t.end_time,
                "text": t.text,
                "duration": (t.end_time or 0) - (t.start_time or 0),
            }
            for t in cached.transcriptions
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
        output_path = self.export_chain.run(output_data, output_format, template_path)
        if progress_callback:
            progress_callback(100, "⚡ 缓存命中")
        return {
            "transcript": transcript,
            "segments": segments,
            "minutes": cached.minutes_text or "",
            "action_items": cached.action_items_text or "",
            "resolutions": cached.resolutions_text or "",
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
    ):
        """Steps 3-7: 分类 → LLM 提取 → 持久化 → RAG 索引 → 导出"""
        # Step 3: 分类
        if progress_callback:
            progress_callback(55, "📊 分析会议特征...")
        duration = max((seg.get("end", 0) for seg in segments), default=0)
        duration_category = ASREngine.classify_duration(duration)
        environment = "unknown"
        meeting_id = self.db.create_meeting(
            title, file_path, duration_category, environment, file_hash
        )

        # 保存术语词表（如有）
        if terms:
            try:
                save_terms(meeting_id, terms)
            except Exception as e:
                logger.warning("保存术语词表失败: %s", e)

        # Step 4: LLM 提取
        if progress_callback:
            progress_callback(65, "🤖 生成会议纪要...")
        date_str = meeting_dt.strftime("%Y-%m-%d %H:%M")
        action_items, resolutions, minutes = self.minutes_chain.run(
            transcript, title=title, date=date_str,
            scene=scene, custom_headings=custom_headings,
        )

        if not (minutes or "").strip():
            if len(transcript or "") > _FALLBACK_TRANSCRIPT_LEN:
                logger.warning(
                    "纪要生成返回空，回退原文截断 (%d -> %d 字符)",
                    len(transcript), _FALLBACK_TRANSCRIPT_LEN,
                )
            minutes = (
                f"# 会议纪要：{title}\n\n**日期**：{date_str}\n\n"
                f"## 转录文本\n{(transcript or '无')[:_FALLBACK_TRANSCRIPT_LEN]}"
            )
        if not (action_items or "").strip():
            action_items = "本次会议未明确待办事项。"
        if not (resolutions or "").strip():
            resolutions = "本次会议未明确决议。"

        # Step 4.5: 摘要 + 项目名生成
        if progress_callback:
            progress_callback(72, "📝 生成摘要...")
        short_summary, project_name = self._generate_summary(transcript, minutes)

        # Step 5: 持久化
        if progress_callback:
            progress_callback(80, "💾 保存结果...")
        self.db.add_transcriptions_bulk(meeting_id, segments)
        self.db.update_meeting_results(
            meeting_id, minutes, action_items, resolutions,
            short_summary=short_summary,
            project_name=project_name,
        )

        # Step 6: 向量索引 (RAG)
        if progress_callback:
            progress_callback(88, "🔍 索引到知识库...")
        try:
            get_retriever().rebuild_meeting_index(
                meeting_id,
                transcript=transcript,
                minutes=minutes,
                action_items=action_items,
                resolutions=resolutions,
            )
        except Exception as e:
            logger.warning("RAG 索引重建失败，已保留旧索引: %s", e)

        # Step 7: 导出
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

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_summary(transcript, minutes):
        """调用 LLM 生成 short_summary 和 project_name。
        失败时返回安全 fallback 值，不抛异常。
        """
        try:
            template_path = (
                Path(__file__).resolve().parent.parent
                / "prompts" / "templates" / "auto_summary.yaml"
            )
            with open(template_path, "r", encoding="utf-8") as f:
                template = yaml.safe_load(f)
            system_prompt = template["system"].format(
                transcript=(transcript or "")[:3000],
                minutes=(minutes or "")[:1000],
            )
        except Exception as e:
            logger.warning("加载 auto_summary 模板失败: %s", e)
            return (minutes or "")[:200], "未分类"

        try:
            llm = get_llm(temperature=0.1)
            response = llm.invoke(system_prompt)
            text = response.content if hasattr(response, "content") else str(response)
        except Exception as e:
            logger.warning("摘要 LLM 调用失败: %s", e)
            return (minutes or "")[:200], "未分类"

        try:
            # 移除可能的 ```json 包装
            text = text.strip()
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
            data = json.loads(text)
            project_name = str(data.get("project_name", "未分类"))[:20]
            short_summary = str(data.get("short_summary", ""))[:200]
            return short_summary, project_name
        except (json.JSONDecodeError, TypeError, KeyError) as e:
            logger.warning("摘要 JSON 解析失败: %s, raw=%s", e, text[:100])
            return (minutes or "")[:200], "未分类"

    @staticmethod
    def _estimate_speaker_count_heuristic(segments):
        """启发式估计说话人数，仅供 UI 展示参考，不参与数据分类决策"""
        if not segments:
            return 1
        avg = sum(seg.get("duration", 0.0) for seg in segments) / max(len(segments), 1)
        if avg < 3:
            return 4
        if avg < 5:
            return 3
        if avg < 15:
            return 2
        return 1
