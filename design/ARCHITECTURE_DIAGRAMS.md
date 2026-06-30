# 架构与工作流图

> 配套 [PLATFORM_DESIGN.md](./PLATFORM_DESIGN.md)（终态）与 [MVP_DESIGN.md](./MVP_DESIGN.md)（近期照做）。
> 用 Mermaid 绘制，VS Code（Markdown Preview Mermaid 插件）/ GitHub 可直接渲染；亦见同目录 `ARCHITECTURE_DIAGRAMS.html`（浏览器直开）。

## 图例（颜色 = 来源）

| 颜色 | 含义 |
|---|---|
| 🟢 绿 | **复用成熟开源**（LangGraph / MCP SDK / Postgres / Langfuse 等，不自造） |
| 🔵 蓝 | **从 BAU(bau_center) 移植**（已验证代码抽取/改造） |
| 🟠 橙 | **自建新内核**（平台差异化，无现成件） |
| ⚪ 灰虚线 | **推迟 / Post-MVP**（带触发器，先不建） |

---

## 1. 项目结构

```mermaid
flowchart TB
  classDef oss fill:#d5f5e3,stroke:#1e8449,color:#145a32;
  classDef bau fill:#d6eaf8,stroke:#2471a3,color:#1a5276;
  classDef core fill:#fdebd0,stroke:#ca6f1e,color:#7e5109;
  classDef later fill:#f2f3f4,stroke:#909497,color:#566573,stroke-dasharray:5 3;

  subgraph L0["客户端 / 前端"]
    direction LR
    chatui["Chat UI + 单一 SSE 渲染器<br/>(assistant-ui / Vercel AI SDK)"]:::later
    studio["Studio 配置前端<br/>(表单 + chatbot 引导)"]:::later
  end

  subgraph L1["API / 契约层"]
    direction LR
    contract["SSE 契约 v1alpha1<br/>run_id · call_id · seq · timestamp"]:::bau
    resolver["deployment_id → 不可变 manifest_digest<br/>(服务端定版, 防降级)"]:::core
    reconnect["SSE 断线恢复<br/>id/Last-Event-ID/重放"]:::later
  end

  subgraph L2["agent_core 运行时 · 自建内核"]
    direction TB
    manifest["Manifest 加载/校验"]:::core
    providers["Provider 接口<br/>Tool · Knowledge · Auth · DataScope"]:::core
    identity["身份三分<br/>Principal · Credential · Execution"]:::core
    reactgraph["LangGraph ReAct 图"]:::oss
    dispatch["dispatcher 路由<br/>(读侧 tool-calling)"]:::bau
    gov["工具治理<br/>去重 · runaway上限25 · artifact 旁路"]:::bau
    llm["LLM 工厂<br/>(langchain-openai / LiteLLM 网关)"]:::bau
    gate["写双门<br/>显式mode AND effect AND 确认 AND executor复核"]:::core
    ckpt["会话 checkpointer"]:::oss
  end

  subgraph L3["Plugin · MVP 仅 BAU 一个"]
    direction LR
    toolprov["BAU ToolProvider<br/>(bau_* 工具)"]:::bau
    knowprov["KnowledgeProvider<br/>(domain card)"]:::bau
    datascope["DataScopeAdapter<br/>per-row 行级裁剪 (不可省)"]:::core
    effect["effect 位 read_only/has_side_effect<br/>(人工审核冻结)"]:::core
  end

  subgraph L4["知识层"]
    direction LR
    cards["分区结构化卡片<br/>主键 domain/entity, UI 仅 source_ref"]:::core
    kstore["索引存储<br/>(Postgres FTS / SQLite FTS5)"]:::oss
    appknow["app_knowledge 工具 (enum 检索)"]:::core
    retr["动态工具/卡片检索<br/>(RAG-MCP, >~30 时)"]:::later
    vec["向量兜底 (pgvector)"]:::later
  end

  subgraph L5["工具接入"]
    direction LR
    mcp["MCP 接入<br/>(MCP SDK + langchain-mcp-adapters)"]:::oss
    oapi["OpenAPI 导入→minify→聚类→重塑→review<br/>(LLM-OpenAPI-minifier)"]:::later
    gw["Tool Gateway (直连现成 API)"]:::later
  end

  subgraph L6["写事务"]
    direction LR
    proposal["WriteProposal + 自有 store + confirm 接口<br/>(BAU 现模型, 不依赖 interrupt)"]:::bau
    txn["写事务状态机<br/>DRAFT→…→COMPENSATION, ETag/TOCTOU"]:::later
    durable["Postgres durable checkpoint<br/>(仅 interrupt 式写需要)"]:::later
  end

  subgraph L7["质量 / 安全 / 同步"]
    direction LR
    evalg["最小 eval gate<br/>工具轨迹/scope/不编造"]:::core
    evaltool["Eval/红队工具<br/>(DeepEval/Giskard/promptfoo/DSPy)"]:::oss
    specdiff["spec-diff → 受影响工具/卡片反查<br/>(oasdiff 引擎)"]:::later
    inject["间接注入全套<br/>DLP/egress/MCP签名"]:::later
    audit["审计 (AgentRun)"]:::bau
  end

  subgraph L8["基础设施"]
    direction LR
    pg["PostgreSQL"]:::oss
    queue["Celery + Redis (异步)"]:::oss
    obs["OTel / Langfuse (可观测)"]:::oss
    auth["Keycloak / Casbin (认证/策略)"]:::later
    secret["Vault / KMS (密钥)"]:::oss
  end

  L0 --> L1 --> L2
  L2 --> L3 --> L4
  L2 --> L5
  L2 --> L6
  L2 --> L7
  L2 -.->|依赖| L8
  L4 --> kstore
  L3 --> effect --> gate
  datascope --> gov
```

---

## 2. 运行时工作流（一次 turn）

```mermaid
flowchart TD
  classDef bau fill:#d6eaf8,stroke:#2471a3,color:#1a5276;
  classDef core fill:#fdebd0,stroke:#ca6f1e,color:#7e5109;
  classDef oss fill:#d5f5e3,stroke:#1e8449,color:#145a32;

  A["用户消息 + deployment_id"]:::bau --> B["解析 manifest_digest<br/>绑定 thread/checkpoint"]:::core
  B --> C["建图: 按 actor 裁剪可见工具/分区<br/>(RBAC 反映进 schema)"]:::core
  C --> D{"tool-calling 循环<br/>(读侧无意图分类)"}:::oss

  D -->|怎么用、解释| K["app_knowledge(area)<br/>取分区卡片"]:::core
  D -->|查数据| T["bau_* 数据工具"]:::bau
  T --> DS["DataScopeAdapter<br/>per-row 行级裁剪"]:::core
  DS --> D
  K --> D

  D -->|够答即停| ANS["生成回答<br/>每字段可溯源到工具 (不编造)"]:::core
  ANS --> DONE["SSE: tool_call/result(call_id配对)<br/>→ artifact → answer → done"]:::bau

  D -.检测到变更请求.-> W{"显式 write mode?"}:::core
  W -->|否| NUDGE["提示: 请切换写入模式"]:::bau
  W -->|是, 且 effect=has_side_effect| PROP["生成 WriteProposal<br/>持久化到 store"]:::bau
  PROP --> CONFIRM["用户确认 (人工)"]:::core
  CONFIRM --> EXEC["executor 复核<br/>权限/版本/expiry/幂等 → 执行"]:::core
  EXEC --> DONE
```

---

## 3. 构建工作流（manifest 生产管线 · 多为 Post-MVP）

```mermaid
flowchart LR
  classDef core fill:#fdebd0,stroke:#ca6f1e,color:#7e5109;
  classDef later fill:#f2f3f4,stroke:#909497,color:#566573,stroke-dasharray:5 3;
  classDef bau fill:#d6eaf8,stroke:#2471a3,color:#1a5276;

  SRC["源: GitHub代码 / 上传文件 / swagger / 额外API"]:::later
  SRC --> TL["工具层<br/>MCP 接入 或 swagger→minify→聚类→重塑→人工review"]:::later
  SRC --> KB["知识层<br/>按 domain 分区→LLM 起草卡片→人工审核→入索引(带 provenance+hash)"]:::later
  TL --> MAN["Manifest 组装 (v1alpha1)"]:::core
  KB --> MAN
  MAN --> RB["RBAC + DataScope 配置<br/>(LLM 辅助, 越权代码兜底)"]:::core
  RB --> EV["Eval 黄金集(断言式) + gates"]:::core
  EV --> DEP["部署 staging → 过 gate → prod (版本冻结/可回滚)"]:::core
  DEP --> SY["spec-diff 监控(oasdiff)<br/>→ 受影响工具/卡片反查 → 增量更新"]:::later
  SY --> TL

  MVP["MVP 实际范围: BAU 已有工具/知识直接作为 Provider,<br/>跳过 SRC→TL/KB 导入链, 直接组装 Manifest 跑通行为等价"]:::bau
  MVP -.替代.-> MAN
```

---

## 4. MVP vs 完整设计 一览

```mermaid
flowchart LR
  classDef core fill:#fdebd0,stroke:#ca6f1e,color:#7e5109;
  classDef bau fill:#d6eaf8,stroke:#2471a3,color:#1a5276;
  classDef oss fill:#d5f5e3,stroke:#1e8449,color:#145a32;
  classDef later fill:#f2f3f4,stroke:#909497,color:#566573,stroke-dasharray:5 3;

  subgraph MVP["MVP (P0/P1 现在建)"]
    m1["manifest + agent_core"]:::core
    m2["BAU 作唯一 plugin"]:::bau
    m3["per-row DataScope"]:::core
    m4["读安全 + BAU 现有草案写"]:::bau
    m5["SSE v1alpha1 + call_id 修复"]:::bau
    m6["最小 eval gate"]:::core
    m7["静态 enum 知识检索"]:::core
  end

  subgraph DEC["现在决策,不建机器"]
    d1["身份三分形状 / tenant 预留"]:::core
    d2["知识主键 domain/entity"]:::core
    d3["effect 二元位"]:::core
    d4["v1alpha1 不冻结"]:::core
  end

  subgraph DEF["推迟 (带触发器)"]
    x1["写事务状态机/durable ckpt"]:::later
    x2["完整身份链/多租户"]:::later
    x3["注入全套/MCP签名"]:::later
    x4["动态检索/swagger导入"]:::later
    x5["spec-diff/断线恢复"]:::later
    x6["Studio 前端"]:::later
  end

  MVP --> DEC --> DEF
```
