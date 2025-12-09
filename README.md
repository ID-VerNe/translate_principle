# Translate Principle | AI 深度翻译方法论

![Status](https://img.shields.io/badge/Status-Active-success) ![License](https://img.shields.io/badge/License-MIT-blue)

**Translate Principle** 是一套经过实战验证的 AI 翻译工作流与 Prompt 工程集合。

本项目不仅仅是简单的“翻译指令”，而是通过**分步引导**、**术语锁定**、**自我纠错**和**风格定制**，让 ChatGPT、Claude 或 Gemini 等大型语言模型（LLM）产出媲美专业人工翻译的高质量文本。

## 📖 核心文档

### 1. 文章翻译与润色 (Web UI 版)
> 适用于直接在 ChatGPT / Claude / Gemini 等网页端进行交互式翻译。

👉 **[点击查看：AI 交互式深度翻译手册 (Web UI)](./WebUI.md)**

这套流程通过独特的 **"4+1 步法"** 解决了 AI 翻译常见的“机器味重”、“术语不统一”和“幻觉”问题：
*   **Step 0**: 全局角色设定 (System Prompt)
*   **Step 1**: 术语提取与定义 (Term Extraction)
*   **Step 2**: 逐句直译 (Straight Translation)
*   **Step 3**: 找茬与审校 (Issue Spotting & Critique)
*   **Step 4**: 最终意译与润色 (Final Polish)

---

## 🔮 路线图 (Roadmap)

本项目正在持续迭代中，未来将覆盖更多翻译场景：

- [x] **通用文章/技术文档翻译**：基于 Web UI 的交互式 Prompt 流程。
- [ ] **视频字幕翻译**：针对 SRT/ASS 字幕文件的上下文优化与双语对照流程。
- [ ] **API 自动化脚本**：提供 Python 脚本，将上述 Prompt 流程自动化，支持批量处理（适合开发者）。
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
*Created by [ID-VerNe](https://github.com/ID-VerNe)*
