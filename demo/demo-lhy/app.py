"""
app.py - Streamlit 前端
功能：上传音频 → 实时显示识别结果 → 生成纪要 → 下载文档
"""

import os
import tempfile
import streamlit as st
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ── 页面配置
st.set_page_config(
    page_title="会议纪要助手",
    page_icon="🎙️",
    layout="wide"
)

st.title("🎙️ 会议纪要助手")
st.caption("上传会议录音，自动生成结构化会议纪要")

# ── 侧边栏配置
with st.sidebar:
    st.header("⚙️ 配置")
    whisper_model = st.selectbox(
        "Whisper 模型",
        ["tiny", "base", "small"],
        index=1,
        help="tiny最快，small中文最准"
    )
    ollama_model = st.text_input(
        "Ollama 模型",
        value=os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
    )
    meeting_title = st.text_input("会议标题", placeholder="留空则自动生成")
    export_formats = st.multiselect(
        "导出格式",
        ["Word (.docx)", "Markdown (.md)", "PDF (.pdf)"],
        default=["Word (.docx)", "Markdown (.md)"]
    )

    st.divider()
    st.header("💬 历史会议")
    if st.button("查看历史记录"):
        try:
            from modules.database import list_meetings
            meetings = list_meetings()
            for m in meetings:
                st.write(f"#{m['id']} {m['title']} — {str(m['created_at'])[:10]}")
        except Exception as e:
            st.error(f"数据库连接失败：{e}")

# ── 主区域
tab1, tab2 = st.tabs(["📤 上传处理", "💬 对话问答"])

with tab1:
    uploaded = st.file_uploader(
        "上传会议录音",
        type=["mp3", "mp4", "wav", "m4a", "flac", "ogg"],
        help="支持 mp3/mp4/wav/m4a/flac/ogg 格式，无需预处理"
    )

    if uploaded:
        st.audio(uploaded)

        if st.button("🚀 开始处理", type="primary", use_container_width=True):

            # 保存上传文件到临时目录
            suffix = os.path.splitext(uploaded.name)[1]
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(uploaded.read())
                tmp_path = tmp.name

            title = meeting_title or f"会议_{datetime.now().strftime('%Y%m%d_%H%M')}"

            # ── Step 1: ASR
            with st.status("🎤 正在识别语音...", expanded=True) as status:
                try:
                    # 动态设置 Whisper 模型
                    os.environ["WHISPER_MODEL"] = whisper_model
                    os.environ["OLLAMA_MODEL"]  = ollama_model

                    from modules.asr import transcribe
                    asr_result = transcribe(tmp_path)
                    transcript = asr_result["text"]
                    segments   = asr_result["segments"]
                    # 存入 session_state，供对话框使用
                    st.session_state.last_transcript = transcript
                    # 新会议重置对话历史
                    st.session_state.chat_history = []
                    st.session_state.chat_messages = []

                    st.write(f"✅ 识别完成，共 {len(transcript)} 字，{len(segments)} 段")
                    status.update(label="✅ 语音识别完成", state="complete")
                except Exception as e:
                    st.error(f"ASR 失败：{e}")
                    st.stop()

            # 显示转录结果
            with st.expander("📄 转录文本", expanded=False):
                st.text_area("原始转录", transcript, height=200)

            # ── Step 2: LLM
            with st.status("🤖 大模型生成中...", expanded=True) as status:
                try:
                    from modules.llm import generate_all
                    results = generate_all(transcript)
                    status.update(label="✅ 会议纪要生成完成", state="complete")
                except Exception as e:
                    st.error(f"LLM 失败：{e}")
                    st.stop()

            # ── Step 3: 显示结果
            # normalize_md：
            #   ## 二级标题 → 加粗，前加汉字序号（一、二、三...），各字段独立计数
            #   ### 三级标题 → 普通文字，前加阿拉伯数字序号（1. 2. 3...），各字段独立计数
            #   完全不使用 # 标题语法，避免 Streamlit 字号放大问题
            CHINESE_NUMS = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]

            def normalize_md(text: str) -> str:
                lines = text.split("\n")
                out = []
                h2_count = 0   # 二级标题计数，每个字段独立
                h3_count = 0   # 三级标题计数，每个二级标题下重置
                for line in lines:
                    if line.startswith("## "):
                        h2_count += 1
                        h3_count = 0   # 进入新二级标题，三级序号重置
                        cn = CHINESE_NUMS[h2_count - 1] if h2_count <= len(CHINESE_NUMS) else str(h2_count)
                        title = line[3:].strip()
                        out.append("")
                        out.append("---")
                        out.append(f"**{cn}、{title}**")
                    elif line.startswith("### "):
                        h3_count += 1
                        title = line[4:].strip()
                        out.append("")
                        out.append(f"{h3_count}. {title}")
                    else:
                        out.append(line)
                return "\n".join(out)

            col1, col2 = st.columns(2)
            with col1:
                st.subheader("📋 会议纪要")
                st.markdown(normalize_md(results["summary"]))

                st.subheader("✅ 待办事项")
                st.markdown(normalize_md(results["todos"]))

            with col2:
                st.subheader("🔨 决议事项")
                st.markdown(normalize_md(results["decisions"]))

            # ── Step 4: 存数据库
            try:
                from modules.database import init_db, insert_meeting, insert_transcripts, insert_summary
                init_db()
                meeting_id = insert_meeting(title, tmp_path)
                insert_transcripts(meeting_id, segments, tmp_path)
                insert_summary(
                    meeting_id=meeting_id,
                    summary=results["summary"],
                    decisions=results["decisions"],
                    todos=results["todos"],
                )
                st.success(f"✅ 数据已存入数据库，会议 ID = {meeting_id}")
            except Exception as e:
                st.warning(f"⚠️ 数据库存储失败（不影响导出）：{e}")

            # ── Step 5: 导出文档
            doc_data = {
                "title":      title,
                "date":       datetime.now().strftime("%Y年%m月%d日"),
                "transcript": transcript,
                "summary":    results["summary"],
                "todos":      results["todos"],
                "decisions":  results["decisions"],
            }

            st.subheader("📥 下载文档")
            dl_cols = st.columns(3)

            if "Word (.docx)" in export_formats:
                try:
                    from modules.exporter import export_word
                    word_path = export_word(doc_data)
                    with open(word_path, "rb") as f:
                        dl_cols[0].download_button(
                            "⬇️ 下载 Word",
                            f,
                            file_name=os.path.basename(word_path),
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                        )
                except Exception as e:
                    dl_cols[0].error(f"Word 导出失败：{e}")

            if "Markdown (.md)" in export_formats:
                try:
                    from modules.exporter import export_markdown
                    md_path = export_markdown(doc_data)
                    with open(md_path, "rb") as f:
                        dl_cols[1].download_button(
                            "⬇️ 下载 Markdown",
                            f,
                            file_name=os.path.basename(md_path),
                            mime="text/markdown"
                        )
                except Exception as e:
                    dl_cols[1].error(f"Markdown 导出失败：{e}")

            if "PDF (.pdf)" in export_formats:
                try:
                    from modules.exporter import export_pdf
                    pdf_path = export_pdf(doc_data)
                    with open(pdf_path, "rb") as f:
                        dl_cols[2].download_button(
                            "⬇️ 下载 PDF",
                            f,
                            file_name=os.path.basename(pdf_path),
                            mime="application/pdf"
                        )
                except Exception as e:
                    dl_cols[2].error(f"PDF 导出失败：{e}")

            # 清理临时文件
            os.unlink(tmp_path)

with tab2:
    st.subheader("💬 对话问答")
    st.caption("可以基于已处理的会议内容进行追问")

    # session_state 初始化
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    if "last_transcript" not in st.session_state:
        st.session_state.last_transcript = ""
    if "chat_messages" not in st.session_state:
        # chat_messages 存储对话历史，格式：[{"role": "user/assistant", "content": "..."}]
        # 由 chat_chain.py 的 chat() 函数维护，实现 Memory 管理
        st.session_state.chat_messages = []

    # 显示历史消息
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    # 输入框
    user_input = st.chat_input("输入问题，例如：会议中提到的截止日期是什么时候？")

    if user_input:
        st.session_state.chat_history.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.write(user_input)

        with st.chat_message("assistant"):
            with st.spinner("思考中..."):
                try:
                    from chains.chat_chain import chat
                    reply = chat(
                        user_input=user_input,
                        meeting_context=st.session_state.last_transcript,
                        chat_messages=st.session_state.chat_messages
                    )
                    st.write(reply)
                    st.session_state.chat_history.append({"role": "assistant", "content": reply})
                except Exception as e:
                    st.error(f"对话失败：{e}")