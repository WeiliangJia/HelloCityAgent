# HelloCityAgent 多 Agent 指南

## 0. 项目准备

### 0.1 环境与工具
- Python 3.11+
- Docker Desktop（用于 Redis/Celery）
- VS Code + Codex 扩展（安装后在左侧出现 OpenAI 图标，需登录 OpenAI）
- 公共 GitHub 仓库（新建空库后 `git remote set-url origin <your_repo>`）

### 0.2 运行依赖
```bash
# 启动基础服务（Redis/Celery/Api）
docker compose up -d
```

### 0.3 环境变量
复制模板并填写 Azure OpenAI 相关配置：
```bash
cp .env.example .env.local
```
关键变量（需在 Azure 上创建部署并填入 .env.local）：
- `AZURE_OPENAI_API_KEY`
- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_API_VERSION`（例如 2024-02-15-preview）
- `AZURE_OPENAI_CHAT_DEPLOYMENT`（示例：gpt-4o-mini）

> 未使用 Azure 时，可设置 `OPENAI_API_KEY` 直接访问 `api.openai.com`。

## 1. 项目背景
HelloCityAgent 面向跨国工作者、留学生、旅行者，解决出行落地前后的机票、酒店、签证、交通、保险、身份证件等信息检索痛点。通过多 Agent + 网络搜索（Tavily）+ 摘要 + 反馈的终端体验，降低搜索时间与成本（默认使用 gpt-4o-mini + Tavily），并保留 FastAPI 接口与 RAG 能力，便于接入网页/前端/后端。

## 1.1 架构概览
- **API 层**：`app/api/main.py:46` 起定义 `/chat/{session_id}`，做消息校验、LangGraph 事件驱动、SSE 推流；监听工具调用触发清单生成，推送任务 ID、占位 banner、最终 checklist；`/generate-title` 生成会话标题。
- **多 Agent 编排**：`app/core/graph.py:356` 起的 `AgentState` 装配各代理/QA/搜索工具；`get_router_graph_chat` 以判决→路由→聊天/RAG/搜索→总结（可选监督）组织对话；`get_router_graph_generate`/`get_router_graph_convert` 负责 checklist 生成与元数据提取；各 wrapper 处理异常降级与结构化输出。
- **服务层**：`app/services/message_service.py:5` 校验/转换消息为 LangChain 对象；`app/services/checklist_service.py:7` 提交 Celery、轮询结果、构建“生成中” banner，保证主线程非阻塞。
- **后台任务**：`app/api/tasks.py:1` 初始化 Celery（Redis broker/backend，结果 1 小时过期）；`create_checklist_items` 依次跑生成图与转换图，整理 LLM 产物为前端需要的 checklist/metadata。
- **配置与依赖注入**：`app/config/settings.py:6` 读取 `.env.local`（支持 OpenAI/Azure 多模型）；`app/config/dependencies.py:15` 构建聊天/清单/裁判/摘要模型、Chroma 向量库与简化 RetrievalQA。
- **提示与代理实现**：`prompts/*.txt` 存放提示；`app/agents/` 内含聊天、搜索、清单生成/转换、裁判、RAG、总结、监督等 Agent，由 `AgentState` 注入 LangGraph 节点。

## 1.2 运行流程（终端与接口共用同一图）
- **终端入口**：`cli_chat.py:8-71` 加载 `.env.local`，循环读取输入，累积为 `HumanMessage/AIMessage` 历史，调用 `get_router_graph_chat().astream_events` 流式输出（或 `ainvoke` 单次返回）。
- **主对话图**：`app/core/graph.py:35-210` 以 `judge` 起始；判决路由到 `chatbot`（默认聊天/工具调用）、`rag_agent`（RAG 检索）、`price_search`（需要 Tavily 查询）。搜索结果交给 `summary_agent` 再可选 `supervisor_agent` 反思；否则各节点直接回传。
- **工具触发**：`app/agents/chatbot_agent.py:8-34` React Agent 暴露 `trigger_checklist_generation`（可选 QA 工具）。LLM 触发时事件中可见 tool call。
- **SSE 推流**：`app/api/main.py:47-210` 监听 LangGraph 事件：`on_chat_model_stream` 推 `text-delta`，`on_node_end` 推 summary/search/supervisor 等 payload。检测到 `trigger_checklist_generation` 时提交 Celery，先推 `task-id` + `data-checklist-pending`，等待结果后推 `data-checklist` 或 `data-checklist-error`。
- **清单生成链路**：`app/api/tasks.py:1-250` 的 `create_checklist_items` 使用 `get_router_graph_generate`（`graph.py:214-244`，`websearch_agent`→`checklist_generator`）和 `get_router_graph_convert`（`graph.py:248-257` 提取元数据）产出 checklist，`_build_frontend_checklist` 计算 `dueDate`/`checklistId` 等并返回，主进程 SSE 推送。
- **消息预处理**：`app/services/message_service.py:4-39` 将外部 dict 转成 LangChain 消息，API 与 CLI 共用。

## 2. 终端对话示例
```bash
python cli_chat.py --stream
# 输入示例：
# 你：从上海 3 月底去悉尼待 5 天，帮我找机票顺便给个准备清单
# 代理会先判定是否需要搜索 -> 触发 Tavily -> 汇总价格 -> 可能触发 checklist 工具 -> 返回清单并流式文本
```
示例意图：生成机票搜索方案（会返回搜索摘要），随后触发 checklist，最终 SSE 内含 `data-checklist`。

## 3. 心得体会
Agent/AIOps 工具链显著压缩了交付周期：过去中小型全栈项目需多人月，如今中级开发者借助 Codex/Claude/Cursor + Azure OpenAI 等，可在一周完成约 80% 工作。生态仍在快速演化（如 MCP 协议等），持续学习与适配新工具是开发者保持竞争力的关键。