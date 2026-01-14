# Translate Principle | AI 深度翻译方法论

![Status](https://img.shields.io/badge/Status-Active-success) ![License](https://img.shields.io/badge/License-MIT-blue)

**Translate Principle** 是一套经过实战验证的 AI 翻译工作流与 Prompt 工程集合。

本项目不仅仅是简单的“翻译指令”，而是通过**分步引导**、**术语锁定**、**自我纠错**和**风格定制**，让 ChatGPT、Claude 或 Gemini 等大型语言模型（LLM）产出媲美专业人工翻译的高质量文本。

## 📖 核心文档

### 1. 文章翻译与润色 (Web UI 版)
> 适用于直接在 ChatGPT / Claude / Gemini 等网页端进行交互式翻译。

👉 **[点击查看：AI 交互式深度翻译手册 (Web UI)](WebUi.md)**

这套流程通过独特的 **"4+1 步法"** 解决了 AI 翻译常见的“机器味重”、“术语不统一”和“幻觉”问题：
*   **Step 0**: 全局角色设定 (System Prompt)
*   **Step 1**: 术语提取与定义 (Term Extraction)
*   **Step 2**: 逐句直译 (Straight Translation)
*   **Step 3**: 找茬与审校 (Issue Spotting & Critique)
*   **Step 4**: 最终意译与润色 (Final Polish)

### 2. 视频字幕自动化翻译 (CLI 版)
> 适用于批量处理 SRT 字幕文件，基于 Python 脚本的全自动工作流。

*   👉 **[操作指南：如何使用一键翻译工具 (CLI)](subtitle/README.md)**
*   👉 **[技术深挖：CLI 自动化翻译的实现原理](CLI_Implementation.md)**

这一模块将 Web UI 的核心思想代码化，实现了：
*   **自动化流水线**：一键完成术语提取、直译、润色。
*   **并发加速**：大幅缩短长视频翻译时间。
*   **进度保存**：支持断点续传，防止长任务中断丢失。

---

## 🛠️ GUI 辅助工具

为了让翻译流程更加简单易用，本项目提供了两个可视化工具：

### 1. WebUI 提示词助手 (`start_webui_helper.ps1`)
**强烈推荐用于 [WebUi.md](WebUi.md) 流程。**
以往你需要手动复制原文、手动查找术语、手动粘贴 Prompt。现在只需将英文原文放入助手：
- **自动接入术语库**：自动识别原文中已有的专业术语及其说明、翻译指令。
- **一键生成 Prompt**：按照 0-4 步法，点击按钮即可获得完美格式的 Prompt 并自动复制。
- **术语优先**：生成的 Prompt 会包含术语库中的背景信息，强制 AI 遵守。

### 2. 字幕翻译工具 (`start_gui.ps1`)
全自动处理字幕文件（SRT/ASS），支持：
- **术语自发现**：自动扫描整个字幕提取核心术语。
- **分步翻译**：在后台自动完成直译与润色。
- **双语预览**：支持对比翻译效果。

---

## 🔮 路线图 (Roadmap)

本项目正在持续迭代中，未来将覆盖更多翻译场景：

- [x] **通用文章/技术文档翻译**：基于 Web UI 的交互式 Prompt 流程。
- [x] **视频字幕翻译**：针对 SRT/ASS 字幕文件的上下文优化与双语对照流程。
- [x] **API 自动化脚本**：提供 Python 脚本，将上述 Prompt 流程自动化，支持批量处理（适合开发者）。
- [ ] **多风格预设**：增加“学术严谨”、“幽默博客（如 Jeremy Clarkson 风格）”、“新闻通稿”等不同语气的 Prompt 模板。

## 💡 为什么建立这个项目？

目前大多数人使用 AI 翻译时，往往只使用一句简单的指令（"请把下面这段话翻译成中文"）。这种方式虽然快捷，但往往会导致：
1.  **术语漂移**：同一个词在上下文中翻译不一致。
2.  **语序生硬**：保留了过多的英文从句结构，不符合中文阅读习惯。
3.  **缺乏深度**：无法识别原文中的文化梗或隐含的幽默。

**Translate Principle** 致力于通过结构化的 Prompt Engineering（提示词工程），让 AI 学会像人类译者一样思考：先理解术语，再直译，再校对，最后润色。

## 🤝 贡献与反馈

如果你有更好的 Prompt 技巧或发现了流程中的缺陷，欢迎提交 Issue 或 Pull Request！

---
*Created by [VerNe](https://github.com/ID-VerNe)*
