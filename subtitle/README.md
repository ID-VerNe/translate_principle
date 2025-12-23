# 🚀 AI 视频字幕自动化翻译 (CLI 版)

本工具提供了一套基于 **LLM (大语言模型)** 的全自动视频字幕翻译工作流。相比于 Web UI 的手动交互，CLI 版本适合**批量处理**、**长视频翻译**以及**追求一致性**的场景。

---

## ✨ 核心优势

*   **全自动流水线**：一键完成“术语提取 -> 直译 -> 润色”全过程。
*   **智能术语管理**：先提取全局术语表，确保专有名词在全片翻译中的一致性。
*   **上下文感知润色**：润色阶段会参考上文，确保语气连贯，解决指代不清的问题。
*   **并发加速**：直译阶段支持并发请求，大幅提升长视频翻译速度。

---

## 🛠️ 准备工作

### 1. 环境配置

确保你已安装 Python 3.10+。

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

## 🚀 使用流程

### 第一步：定制 Prompt (关键！)

AI 需要知道视频的主题才能准确提取术语。在运行前，**必须**检查并修改 `subtitle/prompts/term_extract.prompt`。

1.  打开 `subtitle/prompts/term_extract.prompt`。
2.  找到 `# Context` 部分，修改为你当前视频的主题。
    ```markdown
    # Context
    这是一部关于**{{在此处填写你的视频主题}}**的视频。
    ```

**预设模版**：
我们在 `subtitle/prompts/` 下提供了一些预设模版，你可以直接复制内容覆盖到 `term_extract.prompt` 中：
*   `term_extract.clarkson.prompt`: 适用于《克拉克森的农场》。
*   `term_extract.grandtour.prompt`: 适用于《The Grand Tour》。
*   `term_extract.restoration.prompt`: 适用于古董车修复类节目。

### 第二步：准备字幕文件

将你的英文字幕文件（`.srt`）放入 `subtitle` 目录（或其他你方便的路径）。
*   示例文件：`my_video.srt`

### 第三步：运行翻译命令

使用 `translate_srt_llm.py` 启动翻译。

**基础用法**：
```powershell
python translate_srt_llm.py -i "my_video.srt" -o "my_video_cn.srt"
```

**常用参数**：
*   `-i`, `--input-file`: 输入的 SRT 文件路径（必选）。
*   `-o`, `--output-file`: 输出的 SRT 文件路径（默认在文件名后加 `_output`）。
*   `--no-bilingual`: 仅输出中文（默认为双语对照）。
*   `--batch-size`: 批次大小，默认 8。显存/并发限制较大时可调小。
*   `--max-concurrent`: 直译阶段的最大并发数，默认 4。

**示例：纯中文输出，并发数为 6**
```powershell
python translate_srt_llm.py -i "episode_01.srt" -o "episode_01_cn.srt" --no-bilingual --max-concurrent 6
```

### 第四步：查看结果

1.  **翻译结果**：保存在你指定的输出文件（如 `my_video_cn.srt`）。
2.  **术语表**：生成的术语表会保存在 `current_task_glossary.json`，你可以检查它以确认 AI 提取的术语是否准确。
3.  **日志**：查看 `translation.log` 了解详细运行过程。

---

## 🧩 高级配置

### 1. 手动修正术语
如果 AI 提取的术语有误，你可以：
1.  运行脚本，等待 "Step 1: 构建术语表" 完成。
2.  脚本会生成 `current_task_glossary.json`。
3.  **中断脚本** (Ctrl+C)。
4.  手动编辑 `current_task_glossary.json`，修正或添加键值对。
5.  **重新运行命令**，脚本会优先加载现有的 `current_task_glossary.json`，而不会重新提取。

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

**Q: 用什么模型合适**
A: 目前本地测试使用 **GPT-OSS-20B** ，在线API测试使用小米 **mimo-v2-flash** 和 谷歌 **Gemini-3-Pro**。其他模型可以自行测试。
