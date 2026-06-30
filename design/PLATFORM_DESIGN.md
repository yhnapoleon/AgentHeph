# Agent Chatbot 平台 — 完整设计方案

> 状态：设计草案 v0.1 · 日期 2026-06-29
> 目标：把 BAU Center 已验证的 agent 框架泛化为一个**可为任意内部 app 快速生成对话助手**的平台。
> 本文是单一事实源；改这里 = 改设计，需评审。

---

## 0. 决策基线（已拍板）

| 维度 | 选择 | 含义 |
|---|---|---|
| 技术路线 | **自建内核 + 借基础设施** | manifest / per-row RBAC / 安全闸门 / prompt 纪律 / spec-diff 自建；runtime 用 LangGraph；向量、异步、可观测借成熟件 |
| 工具协议 | **MCP 为主，OpenAPI 导入为辅** | 目标 app 的 API 优先包装成 MCP server；也支持直接吃 swagger 生成工具 |
| 知识层 | **分区结构化卡片 + tool-calling 检索**（非内容 RAG） | 知识按 tab/region 切成精确小卡，按需 tool 调；规模化时对“卡片描述”做轻量检索 |

**调研结论支撑（避免重复造轮子）：**
- per-row 数据级 RBAC、read/guide/write 安全闸门、反编造 prompt 纪律、spec-diff —— 现有平台（Dify / Langflow / Flowise / LibreChat / Copilot Studio）**都不具备或很弱**，是本平台的自建内核与差异化。
- 向量库抽象、异步 worker（Celery+Redis）、OTel 可观测、可视化 LangGraph —— 行业已成熟，**借用不自造**。
- OpenAPI→工具 token 爆炸、工具数 >30 选择退化、分层规划、RAG-MCP 式工具检索 —— 学术界已踩明白，方案里直接采纳（见 §6、§5.4）。

---

## 1. 愿景与范围

### 1.1 是什么
一个**声明式、可生成**的对话助手平台：给定一个内部 app（GitHub 代码 / 上传文件 / swagger / 额外 API），通过填表或 chatbot 引导，产出一份 **manifest**，runtime 据此跑出一个**按用户权限裁剪、读默认安全、写需人工确认**的 app 助手。

### 1.2 不是什么（明确不做，防止范围蔓延）
- ❌ 不是通用 agent 平台 / 不与 LangChain 生态竞争。
- ❌ 不做开放域聊天、不做面向 C 端的营销 bot。
- ❌ 默认**不做内容向量 RAG**（仅在大而散语料时作为某分区的可选实现，见 §5.4）。
- ❌ 不做让 LLM 直接 mutate 业务数据的能力（写必经草案+确认）。

### 1.3 甜区（一句话定位）
**面向内部业务系统、按终端用户权限裁剪、工具直查/操作 app、读安全写确认、带流式前端的对话助手工厂。**

---

## 2. 核心理念：一切都是在编辑一份 manifest

```
        ┌─────────────────────────────────────────────┐
        │  Studio 前端（表单 / chatbot 引导）            │   ← 最后一公里，可换皮
        │  本质 = manifest 编辑器                        │
        └───────────────────────┬─────────────────────┘
                                 │ 产出/编辑
                                 ▼
        ┌─────────────────────────────────────────────┐
        │            Manifest（声明式契约）              │   ← 最该先冻结
        │  app 描述 · 能力 · 工具 · 知识分区 · RBAC ·    │
        │  prompt 槽 · 模型 · eval 集 · 版本             │
        └───────────────────────┬─────────────────────┘
                                 │ 消费
                                 ▼
        ┌─────────────────────────────────────────────┐
        │         Runtime（agent_core，吃 manifest）     │   ← 自建内核
        │  LangGraph 图 · 工具封装 · 知识检索 · 安全闸门 ·│
        │  RBAC 注入 · SSE 契约 · 审计                    │
        └─────────────────────────────────────────────┘
```

> **纪律（沿用 BAU）**：backend-first、契约先冻结、前端最后收口。先让 BAU 能被一份 manifest 完整表达、runtime 跑通，再做生成 manifest 的 Studio。

---

## 3. 总体架构

### 3.1 分层

| 层 | 职责 | 自建/借用 |
|---|---|---|
| **agent_core（runtime）** | 建图、流式、工具封装与治理、知识检索、安全闸门、RBAC 注入、SSE、审计 | **自建** |
| **plugin（每 app 一个）** | ToolProvider、KnowledgeProvider、AuthAdapter、DataScopeAdapter | **接入方实现**（平台给接口+脚手架） |
| **Studio** | manifest 编辑、swagger 导入、卡片生成、RBAC 配置、diff、eval 触发 | **自建（最后做）** |
| **基础设施** | 向量库抽象、Celery+Redis 异步、OTel 可观测、PostgreSQL | **借用** |

### 3.2 与 BAU 现有代码的映射
- `agent_core` ← 抽自 [chat.py](../bau_center/src/core/agent/chat.py) 的建图/流式/事件映射 + [assistant.py](../bau_center/src/core/agent/assistant.py) 的 dispatcher + [tools.py](../bau_center/src/core/agent/tools.py) 的 `_run` 治理（去重/上限/session）+ [llm.py](../bau_center/src/core/agent/llm.py) 工厂。
- BAU 整体降级为 **第一个 plugin**：`bau_*` 工具 = 它的 ToolProvider，domain card = 它的 KnowledgeProvider，`CurrentUser` 裁剪 = 它的 DataScopeAdapter。
- SSE 契约 [AGENT_CHAT_CONTRACT.md](../bau_center/docs/AGENT_CHAT_CONTRACT.md) 直接升格为平台契约。

---

## 4. Manifest Schema 草案

> manifest 是声明式 YAML/JSON。下面是字段骨架（值为示例/说明）。

```yaml
apiVersion: agentstudio/v1
kind: ChatbotManifest
metadata:
  id: bau-center
  version: 7              # 自增；部署即冻结一个版本，可回滚
  display_name: "BAU 运维助手"
  description: "银行 ML 平台 BAU 值班助手"   # 进 prompt 的 app 描述

capabilities:             # §7
  - read                  # 查询/分析（默认）
  - guide                 # 解释/怎么用（吃知识层）
  - propose_write         # 产出待确认草案；无 "direct_write" 这一档

model:                    # §映射 llm.py
  endpoint_ref: bank-gateway          # 指向凭据库，不内联
  default: gpt-oss-120b
  light: gemma-3-27b-it                # 分类/便宜活
  vision: OCBC-VLM-BeamSearch
  api_format: openai

tools:                    # §6
  sources:
    - type: mcp           # 首选
      ref: bau-mcp-server
    - type: openapi       # 辅助
      spec_ref: cml-swagger.json
      reshape: true       # 必须经重塑，不 1:1 映射
  selection:              # 用户在 Studio 勾选的可调度范围（按 swagger 聚类）
    enabled_groups: [issues, jobs, runbook, mmp_live]
  governance:
    per_tool_call_limit: 25            # runaway 上限（BAU 实证不可低于此）
    dedup_exact_repeats: true

knowledge:                # §5  分区结构化卡片
  partitions:
    - area: issues
      sources: [{type: swagger, path: /issues}, {type: ui, component: IssuesTab}]
    - area: runbook
      sources: [{type: doc, glob: "docs/runbook/*.md"}]
  discovery: enum         # area<30 用 enum；>=30 切 retrieval（见 §5.4）

rbac:                     # §8
  principal_adapter: bau.AuthAdapter        # 接入方实现
  data_scope_adapter: bau.DataScopeAdapter  # per-row 裁剪，平台抽不掉
  area_to_role:           # 分区可见性 = tab 可见性
    issues: [bau_member, viewer]
    runbook: [bau_member]
  # 工具/能力可见性也在此声明

prompt:                   # §9
  discipline_profile: strict-internal       # 框架固定纪律骨架（写死）
  slots:                  # 仅填槽，LLM 辅助 + 人工 review
    domain_card_ref: bau-domain-card
    tool_routing_ref: bau-tool-routing
    language: mirror-user

eval:                     # §12  一等公民
  golden_set_ref: bau-golden-questions
  gates: [no_fabrication, scope_respected, correct_tool_routing]

sync:                     # §11  spec-diff
  track_specs: [cml-swagger.json, bau-mcp-server]
  snapshot_hash: "sha256:..."

audit:
  sink: agent_run_table
  retention_days: 365
```

**关键原则**：manifest 里**不内联密钥**（只放 `*_ref` 指向凭据库）；**不内联大段 prompt/卡片**（放 `*_ref` 指向受版本管理的内容库）。

---

## 5. 知识层：分区结构化卡片

### 5.0 KB 服务谁：双读者模型（先定位）
知识同时服务**用户**和 **agent**——不是二选一。一张卡两个读者：

| 用途 | 读者 | 例子 | 承载 |
|---|---|---|---|
| ① guide 内容（用户向） | 终端用户（经 agent 转述） | "怎么用 SLA 筛选""这个 tab 干嘛" | 卡片 `body_md` |
| ② agent 操作知识（内部） | agent 自己 | 该调哪个工具、enum 含义、实体关联、数据源分层纪律 | 薄骨架常驻 prompt + 细节下沉卡片 |
| ③ 共享语义核（喂①也喂②） | 两者 | 字段含义、enum 语义、术语、实体模型 | 卡片（`kind=field/enum`） |

- **桥**：卡片的 `related_tools` 对用户无意义，但告诉 agent“看完这张卡下一步调哪个工具”。→ 同一张 `status` enum 卡：`body_md` 向用户解释含义（①），enum 语义让 agent 正确构造 `list_issues(status=...)`（②）。**一次构建，两处复用。**
- **prompt 常驻 vs 卡片按需**：agent 在检索前就需要的东西（主要工具家族 + 数据源分层 + 反编造/调用克制纪律）留 system prompt 当薄骨架；其余 per-area 路由/enum 明细/术语全文下沉成卡片按需取（省 token，也是 BAU 那 200 行 prompt 能瘦下来的原因）。
- 对照 BAU：现状把②全塞 system prompt（[chat.py](../bau_center/src/core/agent/chat.py)）+ 兜底 `bau_domain_glossary`；新架构 = 薄骨架留 prompt + 细节下沉卡片。

### 5.1 三类知识必须分开（最易翻车处）
| 类型 | 内容 | 归属 | 时效 |
|---|---|---|---|
| 实时业务数据 | issue、order、user 的具体值 | **数据工具**（实时查） | 动态，绝不进卡片 |
| 应用/功能知识 | tab 干嘛、字段含义、enum 语义、怎么操作 | **知识卡片** | 半静态 |
| 能力/路由知识 | 有哪些端点、该调哪个工具 | **工具 schema 本身** | 随 spec |

> 铁律：卡片只说“怎么看/什么意思”，**值永远来自数据工具**。在卡片 `kind` 上约束、在 prompt 加一条强制。违反 = BAU 反复强调的“stored 与通用建议混排 / 用静态卡答实时值”灾难。

### 5.2 卡片 schema
```json
{
  "area": "issues",
  "topic": "sla_risk_filter",
  "kind": "feature | field | enum | howto | endpoint",
  "title": "SLA 风险筛选",
  "body_md": "在 Issues 页勾选 'SLA risk only'…",
  "related_tools": ["list_issues"],
  "source_refs": [
    {"type":"swagger","path":"/issues","op":"get"},
    {"type":"ui","component":"IssuesTab"},
    {"type":"code","file":"src/.../issues.py"}
  ],
  "content_hash": "sha256:…",
  "rbac": ["bau_member","viewer"]
}
```
存储 = 一张**简单索引表**，主键 `(area, topic)`，区内大卡加 FTS。**不是向量库。** `content_hash` 复用 BAU 的指纹/陈旧检测范式（[assistant.py `_payload_hash`](../bau_center/src/core/agent/assistant.py)）。

### 5.3 检索（被 tool-calling 调）
- **默认（area < 30）**：单工具 `app_knowledge(area: Enum, topic?: str)`，enum 写进工具 schema → 模型零成本发现。enum **按当前用户可见分区动态生成**（建图时按 actor 构建 → RBAC 自动反映进 schema）。
- 区内大卡：`topic` 触发卡内 FTS。

### 5.4 规模化：area/工具 >30 时切检索（采纳 RAG-MCP 教训）
研究实证：候选 >30 模型选择退化，>100 显著退化。届时：
- 对**卡片/工具的描述（metadata）**建一层轻量语义索引，按 query 先检索出 ~Top-K 相关 area/工具，再交给 LLM。
- ⚠️ 这是对“描述”做检索，**不是对知识内容做 RAG** —— 坚持不做内容 RAG 的原则不变。
- 实现上等价于一个 `list_relevant_areas(query)` 发现工具，或 MCP-Zero 式按需主动发现。

### 5.5 构建来源（读什么）
卡片是**构建期预计算**（非 query 期 RAG）：主 LLM 读尽下列源、分区起草、人工审核。

| 来源 | 喂出哪类卡 | 主要服务 | BAU 对应 |
|---|---|---|---|
| Swagger / OpenAPI spec | endpoint、param 语义、enum、tag 分组 | ②+③ | CML/MMP swagger |
| MCP server 工具定义 | 工具名/docstring/输入 schema | ② | （新增 MCP 路径） |
| 代码 models/entities | 实体关系、字段约束、enum 定义 | ②③ | `entities.py`/`mmp_entities.py`/`constants.py` |
| 代码 service/校验/常量 | 业务规则、阈值档位语义 | ②③ | `knowledge.py`、analytics service |
| UI 源/元数据 | tab/page 结构、表单字段、label、tooltip、路由 | ① | 前端组件树/router/form schema |
| Docs/README/runbook/交接文档/wiki | 领域解释、术语、操作步骤 | ①③ | docs/、runbook 文本 |
| app 内既有帮助/onboarding 文案 | 直接当 guide 内容 | ① | 现有引导文案 |
| DB enum/config 表 | enum 实际值+标签 | ③ | 字典表 |
| （可选）提问日志/工单 | 不直接成卡——排卡片优先级 + 播种 eval 用例 | — | AgentRun 历史 |

按用途选源：**让 agent 会用工具（②）→ 重点读 swagger/MCP + 代码**；**答好用户 guide（①）→ 重点读 UI + docs + tooltip**；**共享语义（③）→ 代码 enum/constants + swagger enum + 术语文档交叉对齐**。
构建纪律：① 每卡带 `source_refs`（供 §11 spec-diff 反查重建、防编造）；② 卡片禁写实时业务值（§5.1 铁律），值永远来自数据工具。

---

## 6. 工具层：MCP 为主，OpenAPI 为辅

### 6.1 MCP 为主
- 目标 app 的 API 优先包装成 **MCP server**；平台作为 MCP client 接入。面向未来、复用生态、LibreChat 等已力推。
- 接入方写 MCP server（或用平台脚手架从 swagger 生成 MCP server 再人工精修）。

### 6.2 OpenAPI 导入为辅 —— 必须重塑，禁止 1:1
研究实证：原始端点直接转工具 = token 爆炸 + 细粒度啰嗦 + agent loop。流程：
```
swagger → minify（去噪，借 LLM-OpenAPI-minifier 思路）
       → 按 region/tag 聚类（Studio 展示供勾选）
       → LLM 辅助“工具重塑”：合并相关端点为聚合工具、裁剪响应字段、生成紧凑 docstring
       → 人工 review
       → 注册为工具
```
> 对标 BAU：`bau_issue_breakdown`（聚合）替代逐行遍历、`_MAX_ROWS`、truncated meta、紧凑结果 dict（[tools.py 头部](../bau_center/src/core/agent/tools.py)）。重塑就是把这些刻意设计复制到任意 API 上。

### 6.3 工具治理（直接抄 BAU）
- 每轮**精确去重**（同名同参返缓存）、**runaway 上限**（默认 25，BAU 实证不可低于此，曾设 6 误伤合法 fan-out）。
- 每工具调用**注入 actor**、各自开关 session（[tools.py `_run`](../bau_center/src/core/agent/tools.py)）。
- 大数据走 **artifact_sink → SSE**，不进模型 context。

### 6.4 工具选择 = 取代 intent 分类
- 读侧：纯 tool-calling，砍掉读侧意图分类器（Copilot Studio 的 generative orchestration 同思路）。
- 保留**极轻量 fast-path**（关键词直达）纯为延迟/成本，非正确性。

---

## 7. 能力与路由：read / guide / propose_write + 安全闸门

### 7.1 三档能力（无“直接写”这一档）
| 能力 | 行为 | 进入方式 |
|---|---|---|
| read | 查询/分析 | 默认，tool-calling 自由调读工具 |
| guide | 解释/怎么用 | 调知识层 |
| propose_write | 产出**待确认草案**，人工确认后由系统提交 | **显式 mode 切换**，绝不由 LLM 自行进入 |

### 7.2 安全闸门（自建内核，BAU 已验证）
- 写**永不**作为自动路由/tool-calling 的结果出现 —— 复刻 [assistant.py](../bau_center/src/core/agent/assistant.py) “write is NEVER an auto outcome”。
- 写流程 = 生成 `WriteProposal`（结构化草案）→ 前端展示 diff → 用户确认 → 系统执行。LLM 全程不直接 mutate。
- 平台把这套**强制**给所有 plugin，不靠接入方自觉。

---

## 8. RBAC 与身份（差异化核心）

### 8.1 两层，缺一不可
1. **可见性层**（平台做）：哪些工具/分区/能力对该角色可见 → 建图时按 actor 裁剪 enum 与工具集。
2. **行级数据裁剪层**（接入方实现 `DataScopeAdapter`，平台抽不掉）：同一工具内按用户过滤数据行。BAU 靠 `fn(session, actor, ...)`。
> ⚠️ 只做可见性层 = 数据越权事故。off-the-shelf 平台普遍只到 workspace 级，这是本平台必须自建之处。

### 8.2 身份注入
- `Principal` 协议（最小字段：user_id/role/scopes）替代 `CurrentUser`。
- 借鉴 LibreChat 的 per-user 凭据占位符思路注入终端用户身份到工具调用。

### 8.3 LLM 辅助 RBAC（可，但有边界）
- 可让 LLM 建议“area↔role 映射”、查漏、对齐 swagger 权限注解。
- **越权边界必须代码兜底**，LLM 不当裁判。

---

## 9. System prompt 构建

### 9.1 原则：框架写死纪律骨架 + 接入方只填槽
- **写死（discipline_profile）**：反迎合、不编造、语言镜像、调用克制、stored-vs-通用建议分层、三种“没有”要分清 —— 抽自 BAU 的 scar tissue（[chat.py CHAT_SYSTEM](../bau_center/src/core/agent/chat.py)）。
- **填槽（LLM 辅助 + 人工 review）**：app 描述、domain card、工具路由表、enum 语义。
> 禁止让 LLM 自由写整段 prompt —— BAU 的纪律是回归测出来的，生成的 prompt 没有这层免疫。生成的 prompt **必须过 eval 才上线**。

### 9.2 瘦身红利
分区卡片把领域知识移出 prompt → 按需取卡 → 可把 BAU 那 200 行 system prompt 大幅压缩。

---

## 10. 构建工作流（端到端 pipeline）

```
1. 接入源：GitHub 代码 / 上传文件 / swagger / 额外 API
2. 描述 app + 选能力（read/guide/propose_write）
3. 工具层：MCP 接入 或 swagger 导入→minify→聚类→重塑→review
4. 知识层：按 tab/region 分区→LLM 起草卡片→人工 review→入索引库（带 source_refs+hash）
5. RBAC：配置 area/工具/能力↔role；实现 DataScopeAdapter；LLM 辅助查漏
6. Prompt：选 discipline_profile + 填槽（LLM 辅助）→ review
7. Eval：生成/采集黄金问题集 → 跑 gates
8. 产出 manifest（version+1）→ 部署到 staging → 通过 eval → prod
9. 运行后：spec-diff 监控（§11）→ 触发增量更新回到对应步骤
```

---

## 11. spec-diff / 同步功能（独有亮点）

调研中**无任何平台主打此功能**。设计：
- manifest 存上次导入的 spec/MCP schema 快照 + 每张卡/每个工具的 `content_hash` + `source_refs`。
- 代码/swagger/UI 变更时：
  1. 重新拉取 spec → 与快照 **diff**；
  2. 按 `source_refs` 反查**受影响的工具与卡片**；
  3. 重算 hash → 标记“陈旧”；
  4. 产出**逐项 PR 式报告**：新增/删除端点 → 受影响工具、需重生成的卡片、失效的 `related_tools`、孤儿 RBAC 映射、可能陈旧的 prompt 路由行；
  5. 用户逐项确认重建。
- 复用 BAU 的 `_payload_hash` / `_snapshot_is_stale` 范式。

---

## 12. Eval / 质量保障（一等公民，最易被忽略）

> BAU 的全部纪律来自回归。没有 eval，每次改 prompt/工具/卡片都是盲改。
- 每个 bot 配**黄金问题集**：问句 → 期望行为（调对工具？尊重 scope？不编造？路由对？）。
- **gates**（部署前必过）：`no_fabrication`、`scope_respected`、`correct_tool_routing`、`no_pii_leak`、`write_requires_confirm`。
- 分区设计让 eval 更易：可直接断言“问 X → 调了 `app_knowledge('issues')`”。
- 每次 manifest 版本变更自动跑；不过 gate 不允许 promote 到 prod。

### 12.4 自检与持续改进闭环（generate → run → judge → optimize）

> 思路：bot 创建后，由一个强主模型（如 Claude）为每个板块生成用例与判据，跑给目标 bot，
> LLM 评判挑出失败，再**受控地**优化结构。四步风险不对等——前三步成熟可复用，**第四步是唯一危险步，必须套笼子**。

**步骤 1 · 生成用例（主 LLM + 人工审核）**
- ⚠️ 关键修正：工具型 bot 的“标准答案”**不是 LLM 写的散文**（散文 gold 自带编造风险，正是本平台要对抗的）。
  gold = **断言集**：
  - 期望**工具轨迹**（该调哪个工具、参数对不对）—— 可确定性断言，不需 LLM；
  - 期望**落地事实**（必须命中哪些真实字段 / 不得出现哪些，如禁编邮箱）；
  - **scope 断言**（越权数据不得出现）。
  与 §12.2 gates 对齐（`correct_tool_routing` / `no_fabrication` / `scope_respected`）。
- **防同源偏差**：出题模型与评判模型尽量错开；**负面/对抗用例显式播种**（编造、迎合、越权、注入、空数据），
  不能只生成友好正例——LLM 天然漏掉灾难类。
- 人工审核为必须关卡（判据会被当权威，错判据比错 prompt 更隐蔽）。

**步骤 2-3 · 作答 + 检测 + 评判**
- **工具调用检测用确定性断言**（比对实际 tool_calls vs 期望），不交给 LLM。
- **LLM-as-judge 只评模糊部分**（措辞/是否答到点）；用 rubric 打分（G-Eval 式）+ 参考锚定 + 多 judge 投票，
  并用小批人工标注校准。防 judge 已知病：位置/冗长偏置、**自我偏好**（偏袒同族模型）、不稳定。

**步骤 4 · 受控优化（唯一危险步，强制护栏）**
| 风险 | 护栏 |
|---|---|
| Goodhart / 过拟合 eval 集 | **hold-out 集**：优化器永远看不到的保留集才决定能否 promote |
| 打地鼠回归 | 必须**全量 eval gate 通过**，不只修失败子集；版本化 + 回滚 |
| 不可审计的自动改动 | 改动产出**待人工确认的 diff**——复用产品自身 WriteProposal 哲学 |
| 越权/高危被自动改 | **限定动作空间**（见下） |
| 不收敛/震荡 | 限定迭代次数；hold-out 不再单调提升即停、升级给人 |

- **动作空间分级（硬约束）**：
  - ✅ 可自动优化：**prompt 槽** → 用 **DSPy**（针对 metric 在保留集上编译 prompt，原则化、防过拟合）/ TextGrad；
  - ⚠️ 半自动：**知识卡片 / 工具 docstring** 的结构修订 → 用 CC 式 agent，但**产出 diff + 人工 review + 过 hold-out gate**；
  - ❌ **永不自动**：**RBAC、DataScope、工具重塑**（自动改 = 安全事故）。
- 全链沿用产品安全闸门哲学：**propose → 人工确认 → 版本化 → eval gate**；让自改链享受与“写业务数据”同等的不信任级别。
- 触发：按 manifest 变更 / 定时，**非常驻**（成本高）。

**步骤 4 可复用件**：prompt 优化 = **DSPy**（MIPRO/BootstrapFewShot）/ **TextGrad** / **APE**；闭环编排与留痕 = **Langfuse / LangSmith**。

---

## 13. Studio 前端（最后做）

- 本质 = manifest 编辑器，两种形态并存：**填表** + **chatbot 引导**（“你的 app 是做什么的？”逐步问）。
- swagger 聚类可视化勾选工具范围；RBAC 矩阵编辑（LLM 辅助）；卡片 review 界面；spec-diff 的 PR 式确认界面；eval 跑分面板。
- 复用统一 SSE 契约的**单一前端渲染器**（一次写好，所有 bot 复用）。

---

## 14. SSE 契约复用

直接采用 BAU 冻结契约（[AGENT_CHAT_CONTRACT.md](../bau_center/docs/AGENT_CHAT_CONTRACT.md)）：
`meta → tool_call* → tool_result* → artifact* → answer → (error) → done`。
- 新增字段允许（前端忽略未知），改名/删/改语义 = 破坏性变更需评审。
- write 走 `WriteProposal` 事件 + 确认回调。

---

## 15. 安全 / 密钥 / 多租户

- 凭据（LLM 网关 token、GitHub OAuth、目标 API key）**集中存凭据库**，manifest 只放 `*_ref`；支持 per-user OAuth vs service account。
- 多租户：workspace 级隔离（借 Dify 思路）+ per-row 数据隔离（自建）。
- 银行约束：LLM 走内部网关（OpenAI 兼容，[llm.py](../bau_center/src/core/agent/llm.py) 已支持自定义 endpoint + 内部 CA）；数据不出域。

---

## 16. 可观测 / 审计 / 成本

- 审计：每轮落库（kind/user/question/answer/工具调用），复用 BAU `AgentRun`。
- 可观测：OTel 导出（SigNoz/Langfuse），per-step timing。
- 成本：per-tenant token 计量 + 限流 + runaway 上限；light tier 跑便宜活。

---

## 17. 路线图（先 de-risk 再做 Studio）

| 阶段 | 目标 | 验收 |
|---|---|---|
| P0 | 冻结 manifest schema + SSE 契约 | 文档评审通过 |
| P1 | agent_core runtime + 把 BAU 改写成第一个 plugin（行为不变） | BAU 在新内核上跑通、回归全过 |
| P2 | MCP 接入 + OpenAPI 导入→重塑链 + 工具治理 | 接入第二个 app 的 API |
| P3 | 知识分区层 + `app_knowledge` 工具 + 卡片生成管线 | guide 能力可用 |
| P4 | RBAC（可见性+行级适配器）+ 安全闸门通用化 | per-row 越权测试通过 |
| P5 | eval 框架 + spec-diff 同步 | 改 spec 能产出影响报告 |
| P6 | Studio 前端（表单 + chatbot 引导） | 非工程师能产出一个 bot |

---

## 18. 全量踩坑清单

> 格式：**症状 → 原因 → 对策**。按域分类。

### A. 架构与抽象
- A1 **过度抽象税**：只有一个 app 时强行泛化，抽象成本 > 收益。→ 先把 BAU 表达为 manifest 验证，第二个 app 出现再固化通用层。
- A2 **manifest 漂移成上帝对象**：什么都往里塞。→ 内联只放结构，大内容/密钥用 `*_ref`；schema 版本化。
- A3 **runtime 与 plugin 边界模糊**：BAU 专有逻辑漏进内核。→ 用 Provider 接口硬隔离；内核不 import 任何 `bau_*`。
- A4 **契约未冻结就动前端**：来回改协议。→ backend-first，契约先冻结（BAU 已证此纪律有效）。

### B. 知识层
- B1 **卡片混入实时数据值** → 答陈旧值。→ `kind` 约束 + prompt 铁律 + eval gate；卡片只写“怎么看”。
- B2 **三类知识串味**：用静态卡答实时问 / 用实时查答怎么用。→ 工具类型隔离（知识工具 vs 数据工具），复刻 BAU 数据源分层。
- B3 **卡片手写散文与代码漂移** → 越用越错。→ 尽量从 source-of-truth 生成，`source_refs` 支撑再生。
- B4 **粒度失衡**：太细 agent 找不到，太粗一卡塞爆。→ 一 tab 一 area，区内按 kind 切，单卡可整段进 context。
- B5 **分区数破 30 仍用 enum** → 选择退化。→ §5.4 切语义检索（对描述，不对内容）。
- B6 **卡片无 provenance** → 无法溯源、无法定向重建、助长编造。→ 强制 `source_refs` + `content_hash`。

### C. 工具层 / OpenAPI / MCP
- C1 **swagger 1:1 转工具** → token 爆炸 + loop。→ 强制 minify+聚类+重塑+review，禁止 1:1。
- C2 **工具响应体过大** → 撑爆 context。→ 响应裁剪、`_MAX_ROWS`、truncated meta、大数据走 artifact。
- C3 **工具数 >30/100** → 选择退化。→ RAG-MCP 式工具检索 / 按 enabled_groups 收窄。
- C4 **docstring 含糊** → 模型选错工具。→ 紧凑且精确的 docstring（Copilot Studio：好描述决定路由质量）。
- C5 **operationId 缺失/重名** → 工具名冲突。→ 生成时规范化（snake_case、去重、≤60 字符）。
- C6 **MCP server 无鉴权/无 scope** → 越权调用。→ MCP 调用注入 principal，server 侧也校验。
- C7 **同一工具被反复换参重打求全** → 浪费+慢。→ 精确去重 + runaway 上限（≥25，勿过低）。

### D. 路由与安全闸门
- D1 **用 tool-calling 取代写路由 → LLM 自行进入写** → 失控。→ 写永不自动；显式 mode + 草案 + 确认。
- D2 **草案被当成已执行** → 用户以为改了其实没。→ 明确 `WriteProposal` 语义 + 前端 diff + 确认回调。
- D3 **fast-path 关键词误伤** → 该走 guide 的被丢进 qa。→ fast-path 仅为延迟，错了也只在只读侧（无害化设计，复刻 BAU）。

### E. RBAC / 身份 / 越权
- E1 **只做工具可见性、不做行级裁剪** → 数据越权（最严重）。→ 强制 `DataScopeAdapter`，per-row 过滤，越权测试入 eval gate。
- E2 **enum/工具集未按 actor 构建** → schema 暴露无权分区。→ 建图时按 actor 裁剪（BAU 已如此）。
- E3 **LLM 当越权裁判** → 被绕过。→ 边界代码兜底，LLM 只辅助配置。
- E4 **thread/会话可跨用户恢复** → 串号。→ user_id 揉进 checkpoint key（复刻 BAU `_thread_key`）。
- E5 **artifact/preview 泄露越权数据** → 旁路泄漏。→ artifact 也过同一 scope。

### F. Prompt / 纪律
- F1 **LLM 自由写整段 prompt** → 丢失反编造/反迎合免疫。→ 纪律骨架写死，只填槽，过 eval。
- F2 **生成 prompt 未回归** → 静默退化。→ prompt 变更必跑黄金集。
- F3 **领域知识全塞 prompt** → 臃肿+贵。→ 移入分区卡片按需取。
- F4 **多分支 prompt 纪律漂移** → 行为不一致。→ 共享纪律片段单一来源（BAU `SHARED_LANG_RULE` 范式）。

### G. spec-diff / 同步
- G1 **spec 变更无人知** → bot 慢慢说错。→ 定期拉取+diff+告警。
- G2 **diff 后全量重建** → 浪费+引入回归。→ 按 source_refs 定向重建，逐项确认。
- G3 **hash 算法不稳定**（key 顺序/空白）→ 假阳性漂移。→ 规范化序列化后再 hash（复刻 BAU `_payload_hash` sort_keys）。

### H. Eval / 质量
- H1 **没有 eval** → 盲改（头号坑）。→ eval 一等公民，gate 卡 promote。
- H2 **黄金集不覆盖反例**（编造/越权/迎合）→ 漏掉灾难类。→ 显式纳入负面用例。
- H3 **eval 只看“答得像”不看“答得对”** → 假通过。→ 断言工具调用与字段溯源，非仅文本相似。
- H4 **LLM 写散文当 gold answer** → 判据本身带编造风险。→ gold = 断言集（工具轨迹+落地事实+scope），非 prose（§12.4）。
- H5 **出题/定答/评判同源** → 盲点相关、自我偏好。→ 出题与评判模型错开；judge 用 rubric + 多投票 + 人工校准。
- H6 **LLM 出题只生成友好正例** → 漏掉灾难类。→ 显式播种负面/对抗用例（编造/迎合/越权/注入/空数据），借 Giskard/PyRIT/garak。
- H7 **自动优化过拟合 eval 集（Goodhart）** → 不泛化。→ hold-out 集决定 promote；优化器看不到它。
- H8 **自改链打地鼠回归** → 修一坏三。→ 全量 gate 通过才算成功 + 版本化回滚。
- H9 **自改链不可审计 / 改了高危项** → 失控或安全事故。→ 改动产出 diff+人工确认；动作空间分级，RBAC/DataScope/工具重塑永不自动（§12.4）。
- H10 **自改循环不收敛** → 震荡烧钱。→ 限迭代 + 单调性停止条件 + 升级给人；按变更/定时触发非常驻。

### I. Studio 前端 / UX
- I1 **先做花哨 UI，runtime 撑不起** → 返工。→ runtime 先行，Studio 最后。
- I2 **非工程师配不出 RBAC/重塑** → 产出烂 bot。→ LLM 辅助 + 默认安全 + 人工 review 关卡。
- I3 **多 bot 各写前端** → 维护爆炸。→ 单一 SSE 渲染器复用。

### J. 安全 / 密钥 / 凭据
- J1 **密钥内联 manifest** → 泄漏。→ 只放 `*_ref` 指凭据库。
- J2 **GitHub/API 凭据混用 service vs user** → 越权或审计断链。→ 明确 per-user OAuth vs service account 策略。
- J3 **目标 API 被 agent 当跳板打内网** → SSRF/越权。→ allowed_domains 白名单（LibreChat 范式）、只读 GET 兜底层校验。

### K. 多租户 / 隔离
- K1 **租户间数据/向量/缓存串** → 泄漏。→ workspace 隔离 + 索引按租户分区。
- K2 **一个租户的 runaway 拖垮共享 worker** → 邻居受害。→ per-tenant 限流+配额。

### L. 成本 / 性能
- L1 **重活全用大模型** → 贵。→ light tier 跑分类/便宜活（BAU 已分层）。
- L2 **live 实时查被滥用做批量遍历** → 慢。→ prompt+工具层禁止批量 live（复刻 BAU 数据源分层禁令）。
- L3 **长 prompt 每轮重发** → token 浪费。→ 知识移出 prompt、prompt 缓存。

### M. LLM 行为特性
- M1 **幻觉**：编 id/邮箱/步骤/链接。→ 字段溯源铁律 + eval gate；占位邮箱视同无。
- M2 **迎合**：用户反问就改口。→ 反迎合纪律 + 工具复核优先（BAU 已实证）。
- M3 **数值自算**：阈值/SLA/时区现推。→ 只引用工具返回字段，禁止自算。
- M4 **工具 loop / 求全** → 超时。→ 去重+上限+“够答就停”纪律。
- M5 **context 溢出**：大结果/多轮。→ artifact 旁路 + 结果裁剪 + 知识按需取。

### N. 运维 / 版本 / 回滚
- N1 **部署即改、无版本** → 无法回滚。→ 每次部署冻结 manifest version，支持回滚。
- N2 **staging/prod 不分** → 拿用户当小白鼠。→ 必过 eval 才 promote。

### O. 组织 / 流程
- O1 **以为全自动、无人 review** → 烂卡片/烂工具/烂 prompt 上线。→ 关键产物（卡片/重塑工具/prompt）强制人工 review。
- O2 **plugin 所有权不清** → DataScopeAdapter 没人维护出越权。→ 每 plugin 指定 owner，适配器纳入其代码审查。

---

## 19. 附录

### 19.1 术语
- **manifest**：声明式 bot 配置，平台契约核心。
- **plugin**：某 app 的 Provider 实现集合。
- **分区卡片**：按 tab/region 切的结构化知识单元。
- **WriteProposal**：待人工确认的结构化写草案。
- **DataScopeAdapter**：接入方实现的 per-row 数据裁剪适配器。

### 19.2 参考（调研来源）
- Dify（OpenAPI 工具 / RAG KB / workspace RBAC / 向量库工厂）: https://github.com/langgenius/dify
- Dify vs Langflow vs Flowise 对比: https://blog.elest.io/dify-vs-langflow-vs-flowise-which-open-source-llm-app-builder-actually-ships-to-production/
- LibreChat Actions（OpenAPI→工具）/ MCP / per-user 凭据: https://www.librechat.ai/docs/features/agents
- OpenWebUI RBAC: https://docs.openwebui.com/
- LLM-OpenAPI-minifier（spec 去噪）: https://github.com/ShelbyJenkins/LLM-OpenAPI-minifier
- RAG-MCP（工具检索缓解 prompt 膨胀）: https://arxiv.org/html/2505.03275v1
- MCP-Zero（按需主动工具发现）: https://arxiv.org/pdf/2506.01056
- Copilot Studio 生成式编排 / 知识源 / 描述质量决定路由: https://learn.microsoft.com/en-us/microsoft-copilot-studio/guidance/generative-orchestration

### 19.2.1 自检/eval 复用件（§12.4）
- DSPy（prompt 编译/优化）: https://github.com/stanfordnlp/dspy
- TextGrad（文本梯度优化）: https://github.com/zou-group/textgrad
- DeepEval（合成用例 / G-Eval / tool-use 指标）: https://github.com/confident-ai/deepeval
- Ragas（testset 生成 / 评测）: https://github.com/explodinggradients/ragas
- Giskard（LLM 扫描 / 红队用例）: https://github.com/Giskard-AI/giskard
- promptfoo（断言 / llm-rubric / red-team）: https://github.com/promptfoo/promptfoo
- PyRIT（微软红队工具）: https://github.com/Azure/PyRIT
- garak（LLM 漏洞/对抗探测）: https://github.com/NVIDIA/garak
- Langfuse（追踪 / 数据集 / eval）: https://github.com/langfuse/langfuse

### 19.3 与 BAU 代码的复用索引
- runtime 抽取：[chat.py](../bau_center/src/core/agent/chat.py) · [assistant.py](../bau_center/src/core/agent/assistant.py) · [tools.py](../bau_center/src/core/agent/tools.py) · [llm.py](../bau_center/src/core/agent/llm.py)
- 契约：[AGENT_CHAT_CONTRACT.md](../bau_center/docs/AGENT_CHAT_CONTRACT.md)
