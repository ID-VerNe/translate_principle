# 🚀 AI 视频字幕自动化翻译 (CLI 版)

本工具提供了一套基于 **LLM (大语言模型)** 的全自动视频字幕翻译工作流。相比于 Web UI 的手动交互，CLI 版本适合**批量处理**、**长视频翻译**以及**追求一致性**的场景。

---

## 🌟 核心优势

*   **全自动流水线**：一键完成“术语提取 -> 直译 -> 润色”全过程。
*   **智能术语管理**：先提取全局术语表，确保专有名词在全片翻译中的一致性。
*   **上下文感知润色**：润色阶段会参考上文，确保语气连贯，解决指代不清的问题。
*   **并发加速**：直译阶段支持并发请求，大幅提升长视频翻译速度。
*   **ASS 特效支持**：内置自动转换工具，支持生成双语对照、智能分行的 ASS 特效字幕。

---

## 🛠️ 准备工作

### 1. 环境配置

确保你已安装 Python 3.10+ 和 [MKVToolNix](https://mkvtoolnix.download/downloads.html#windows) (用于字幕提取)。

```powershell
# 进入 subtitle 目录
cd subtitle

# (推荐) 创建并激活虚拟环境
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置 API Key

复制 `.env.example` 为 `.env`，并填入你的 LLM API Key。

```powershell
cp .env.example .env
```

编辑 `.env` 文件：
```ini
LLM_API_KEY=sk-xxxxxxxxxxxxxxxxxxxx
LLM_API_URL=https://api.deepseek.com/v1/chat/completions  # 示例地址
LLM_MODEL=deepseek-chat                                   # 示例模型
```

---

## 🚀 完整工作流程 (Workflow)

我们提供了一套完整的工具链，建议按照以下步骤操作，以获得最佳体验。

### 第一步：提取与预处理 (Extract & Pre-process)

此步骤将从你的视频文件 (MKV) 中提取字幕。
*   如果提取出的是 ASS 字幕，脚本会自动将其转换为 SRT 格式。
*   如果提取出的是 SRT 字幕，脚本会直接输出。

**使用方法**:
```powershell
# 在项目根目录下运行
python subtitle/pre-process/01-extract_srt.py "你的视频文件.mkv"
```

**输出**: 脚本会在同目录下生成一个或多个 `.srt` 文件（例如 `视频名_track3_eng.srt`）。

---

### 第二步：LLM 智能翻译 (Main Translation)

此步骤是核心，使用 AI 将英文 SRT 翻译成中文。

**1. 定制 Prompt (关键!)**
AI 需要知道视频的主题才能准确提取术语。在运行前，**必须**检查并修改 `subtitle/prompts/term_extract.prompt`。
找到 `# Context` 部分，修改为你当前视频的主题。
```markdown
# Context
这是一部关于**{{在此处填写你的视频主题}}**的视频。
```

**2. 运行翻译**
```powershell
# 基础用法
python subtitle/translate_srt_llm.py -i "上一步生成的字幕.srt" -o "翻译结果.srt"
```

**常用参数**:
*   `--api-url`: 你的 LLM API 地址。
*   `--model-name`: 你使用的模型名称。
*   `--no-bilingual`: 仅输出中文（默认为双语对照）。
*   `--max-concurrent`: 直译阶段的最大并发数（默认 4）。

---

### 第三步：生成 ASS 特效字幕 (Post-process)

此步骤将翻译好的 SRT 文件转换为格式精美的 ASS 字幕。
它会自动识别中英文，进行智能分行，并应用预设的样式（如字体、大小、边框等）。

**使用方法**:
```powershell
# 将翻译好的 SRT 转换为最终的 ASS
python subtitle/post-process/02-post_process_ass.py "翻译结果.srt"

# (可选) 指定输出文件名
python subtitle/post-process/02-post_process_ass.py "翻译结果.srt" -o "最终成品.ass"
```

**功能**:
*   **智能分行**: 自动将同一时间轴内的中英文拆分为独立的行。
*   **自动样式**: 中文行应用中文样式，英文行应用英文样式（通过 `MarginV` 实现双语上下排列）。

---

## 📚 高级配置

### 1. 手动修正术语
如果 AI 提取的术语有误，你可以：
1.  运行脚本，等待 "Step 1: 构建术语表" 完成。
2.  观察终端输出，找到 **"【当前生效的术语表】"** 及其下方的文件路径。
3.  **中断脚本** (Ctrl+C)。
4.  根据路径找到该 JSON 文件，手动编辑修正或添加键值对。
5.  **重新运行命令**，脚本会优先加载该缓存文件中的术语，而不会重新提取。

👉 **[进阶：如何构建自己的永久语料库？](glossaries/README.md)**
我们提供了一套完整的工具链，帮助你从过往的字幕文件中提取术语，构建属于自己的专业知识库。详情请点击上方链接。

### 2. 调整 Prompt
你可以随时修改 `subtitle/prompts/` 下的 `.prompt` 文件，以调整 AI 的翻译风格：
*   `literal_trans.prompt`: 负责直译，要求准确。
*   `review_and_polish.prompt`: 负责润色，控制口语化程度和语气。

---

## ❓ 常见问题

**Q: 翻译中断了怎么办？**
A: 脚本会自动保存进度到 `.progress.json` 文件。直接重新运行相同的命令，脚本会自动从中断的地方继续翻译。

**Q: 想要强制重新翻译？**
A: 删除输出文件 (`.srt`) 和进度文件 (`.progress.json`) 即可。

**Q: 用什么模型合适？**
A: 目前本地测试使用 **GPT-OSS-20B**，在线API测试使用小米 **mimo-v2-flash** 和 谷歌 **Gemini-3-Pro**。其他模型可以自行测试。

**Q: 运行 `01-extract_srt.py` 报错 "未找到 MKVToolNix 工具"？**
A: 请确保你已经安装了 MKVToolNix，并且把安装目录（例如 `C:\Program Files\MKVToolNix`）添加到了系统的 **环境变量 Path** 中。添加后需要重启终端才能生效。

**Q: 生成的字幕有乱码怎么办？**
A: 脚本默认使用 UTF-8 编码处理所有文件。如果你的源文件是 GBK 或其他编码，请先将其转换为 UTF-8。Windows 记事本 "另存为" 时选择编码为 UTF-8 即可。

**Q: 如何修改生成的 ASS 字幕样式（字体、颜色、大小）？**
A: `02-post_process_ass.py` 使用 `subtitle/post-process/asshead.txt` 作为样式模板。你可以直接编辑这个 txt 文件，修改 `[V4+ Styles]` 下的参数。建议使用 Aegisub 打开一个生成的 ass 文件，调好样式后，把头部信息复制回 `asshead.txt`。

**Q: API 报错 429 (Too Many Requests) 或超时？**
A: 这是因为并发数过高或 API 提供商限制了速率。
1. 尝试降低 `--max-concurrent` 参数（例如改为 2 或 1）。
2. 在 `.env` 或代码中增加重试等待时间。

**Q: 为什么生成的 ASS 字幕有时候中英文没有分行显示？**
A: 脚本是根据“一行中文、一行英文”的逻辑来自动分行的。如果翻译结果中，某一块只有中文或只有英文，或者中英文混在同一行（未换行），脚本可能无法正确识别。请检查中间的翻译结果 SRT 文件，确保 LLM 输出的格式是规范的双语对照格式。
