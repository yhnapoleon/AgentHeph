# Agent Chatbot 平台 — MVP 设计

> 状态：MVP 草案 v0.1 · 日期 2026-06-29
> 配套文档：完整愿景见 [PLATFORM_DESIGN.md](./PLATFORM_DESIGN.md)；**本文是近期真正要做的精简范围**。
> 一句话：完整设计是"终态"，本文是"先交付什么、什么先别建"。

---

## 0. 为什么单独写这份

完整设计经两轮评审后累积出大量**生产硬化 + 多租户机器**（写事务状态机、完整身份链、注入全套防线、动态工具检索、断线恢复…）。这些**正确**，但**不是 MVP 阶段该建的**——评审天然只做加法。本文用一把尺子把它们分开：

> **架构决策（改起来贵）现在就定；实现机器（改起来不贵、且有明确触发条件）一律推迟。**

---

## 1. MVP 要证明什么（唯一判据）

> **把 BAU 表达成一份 manifest、跑在 agent_core 上、行为与今天等价。**

BAU 今天已能跑、已有 per-row 权限、读安全、读+guide+(草案式)写。所以 **MVP 本质是一次抽取/重构**，成功 = "BAU 还是那个 BAU，只是改由 manifest 驱动 + 跑在可复用内核上"。

不达成此点之前，不碰第二个 app、不碰 Studio、不碰多租户。

---

## 2. 决策规则（贯穿全文）

| 桶 | 含义 | 处理 |
|---|---|---|
| **现在建** | MVP 本体 + BAU 已有的能力 + 极廉价的正确性修复 | 做 |
| **现在决策，先不建机器** | 改起来贵的 schema 形状 / 数据主键 / 字段预留 / 红线规则 | 只定形状与规则，零成本前向兼容 |
| **推迟（带触发器）** | 昂贵的实现机器，有明确触发条件 | 进 §8 附录，到触发条件再建 |

⚠️ "精简"≠"砍安全"：**per-row 权限、读安全、字段证据链是 BAU 已有的，不做 = 功能倒退**，属"现在建"，绝不推迟。

---

## 3. MVP 范围内（现在建）

1. **manifest + agent_core runtime**：吃一份 manifest，建 LangGraph ReAct 图，跑读+guide+草案写。
2. **BAU 作为第一个、且唯一的 plugin**：`bau_*` 工具 = ToolProvider；domain 知识 = KnowledgeProvider；`CurrentUser` 裁剪 = DataScopeAdapter。
3. **per-row DataScopeAdapter**：每次工具调用注入 actor、按行裁剪（沿用 BAU [tools.py `_run`](../bau_center/src/core/agent/tools.py) 范式）。**差异化核心，不可省。**
4. **读安全 + BAU 现有草案式写**：写仍走"显式 write mode → 生成 `WriteProposal` 持久化到 store → 独立 confirm 接口执行"（BAU 今天就是这个模型，proposal 存在自有 store、**不依赖 langgraph interrupt/checkpoint resume**，故 durable checkpoint 此阶段非必需）。
5. **SSE 契约 v1alpha1**（§5）：含 `call_id` 配对修复 + 预留多 bot 字段。
6. **最小 eval harness**（§7）：黄金集断言"工具轨迹对 / scope 不越权 / 不编造"，作为 promote gate。
7. **工具治理**：沿用 BAU 的去重 + per-tool runaway 上限(25) + 大数据走 artifact。

验收：BAU 的现有回归集在新内核上**全过**，行为等价。

---

## 4. 现在决策、先不建机器（廉价前向兼容）

只定"形状与规则"，不建对应系统：

- **schema 版本号 = `v1alpha1`**（不冻结 `v1`；两个不同 app 跑通后再冻 `v1beta1/v1`）。
- **知识主键 = domain/entity/capability**，UI page/component 只作 `source_ref`（避免 UI 重构时知识大面积漂移）。详见 §6。
- **身份三分**（避免上帝对象，先定形状）：
  ```yaml
  Principal:          { issuer, subject, tenant_id, roles, scopes }
  CredentialContext:  { mode, audience, delegated, token_ref }    # MVP 只用 service_account/银行现有 auth
  ExecutionContext:   { deployment_id, manifest_digest, run_id, thread_id }
  ```
  MVP 只有 BAU 一个 deployment、单租户：`tenant_id` 等字段**预留**，不建多租户/OAuth 委托机器。
- **工具 effect 位（二元）**：每工具声明 `effect: read_only | has_side_effect`（驱动安全闸门）。完整 effect/security/runtime 元数据块**推迟**。
- **请求只带 `deployment_id`**，服务端解析到不可变 `manifest_digest` 并绑定到 thread/checkpoint（防降级攻击）；可选 `expected_revision` 仅用于提示客户端页面过期。

---

## 5. 红线规则（零成本，MVP 即生效）

规则改对不增加工作量，故即使 MVP 也守。摘自宪法 skill，并吸收评审修正：

- **R1 写双门**：有副作用工具**不得在 read/guide mode 暴露或执行**；**仅显式 write mode** 下可生成 `WriteProposal`；executor 执行前**再次校验**权限/版本/expiry/幂等。即 `显式 mode AND effect 强制 AND 人工确认 AND executor 复核`——**effect 不取代 mode，是叠加**。未知 effect 默认拒绝。
- **R-effect 不可自动信任**：`effect` 位由 LLM 起草后**必须人工审核并冻结**；危险工具被误标 `read_only` = 绕过整个安全模型。
- **R-untrusted**：不可信内容（工具结果、工单/文档正文、MCP tool description）**不得进入 system/developer 等高权限指令通道**，只能作为带 provenance/trust/data-boundary 的普通数据输入；**不得借此改变工具集、授权、纪律或执行策略**。
- **R2 per-row 不可省、RBAC/DataScope 永不自动改**（同完整设计）。
- **R3 不编造**：每个字段可溯源到工具返回。
- **R-manifest**：实际运行版本由服务端 deployment 决定，客户端只选 `deployment_id`。

---

## 6. 精简契约 v1alpha1

**请求**：
```json
{ "deployment_id": "bau-center-prod", "message": "...", "thread_id": "...?", "client_request_id": "...?" }
```
服务端：`deployment_id → manifest_digest`（不可变），绑定到 thread/checkpoint。

**事件 envelope**（统一）：
```json
{
  "schema_version": "1", "event": "tool_call",
  "run_id": "...", "thread_id": "...", "seq": 4, "timestamp": "...",
  "data": { "call_id": "...", "tool": "...", "args_preview": {} }
}
```
- `call_id` 必须：并行调同一工具时，仅靠工具名无法配对 `tool_call/tool_result`（修复 BAU [chat.py `_events_for_message`](../bau_center/src/core/agent/chat.py) 的真 bug）。
- `run_id` = 一次 turn；`thread_id` = 整段会话；顺序以服务端 `seq` 为准（`timestamp` 仅观测，不用于安全排序）。
- **thread key** = `tenant / deployment / subject / thread` + 绑 `manifest_digest`（bot 升级后旧会话不在新配置上恢复）。

事件集沿用 BAU：`meta → tool_call* → tool_result* → artifact* → answer → (error) → done`。
**推迟**：SSE `id:`/`Last-Event-ID`/重放、proposal 跨 run 恢复（→ §8）。

---

## 7. 精简 manifest（MVP 子集）

```yaml
apiVersion: agentstudio/v1alpha1
kind: ChatbotManifest
metadata: { id: bau-center, version: 1, display_name: "BAU 运维助手", description: "..." }
capabilities: [read, guide, propose_write]      # propose_write = BAU 现有草案式
model: { endpoint_ref: bank-gateway, default: gpt-oss-120b, light: gemma-3-27b-it, api_format: openai }
tools:
  provider: bau.ToolProvider                    # MVP 直接用 BAU 工具，不走 swagger 导入
  effects: { bau_list_issues: read_only, ... , <写工具>: has_side_effect }  # 人工审核冻结
  governance: { per_tool_call_limit: 25, dedup_exact_repeats: true }
knowledge:
  partitions:                                   # 按 domain/entity，UI 仅作 source_ref
    - area: issue_management
      sources: [{type: swagger, path: /issues}, {type: ui, component: IssuesTab}]
  discovery: enum                               # 工具/分区 <30，静态 enum
rbac:
  principal_adapter: bau.AuthAdapter
  data_scope_adapter: bau.DataScopeAdapter      # per-row，不可省
prompt: { discipline_profile: strict-internal, slots: { domain_card_ref: ..., tool_routing_ref: ... } }
eval: { golden_set_ref: bau-golden, gates: [no_fabrication, scope_respected, correct_tool_routing, write_requires_confirm] }
# 预留字段（先占位，不建机器）：tenant_id / credential_context / sync(spec-diff) / audit retention
```

**推迟**：swagger 导入→重塑链、动态工具检索、completed effect 元数据、spec-diff sync（→ §8）。

---

## 8. Deferred / Post-MVP（带触发器，一条不丢）

| 项 | 触发条件（到此才建） |
|---|---|
| 写事务状态机（DRAFT→…→COMPENSATION、ETag/TOCTOU/idempotency） | 上线第一个需要强一致写的 bot |
| langgraph-interrupt 式写 + **Postgres durable checkpoint** | 改用 interrupt 承载写流程时（BAU 现模型不需要） |
| 完整身份链（issuer/audience/credential_mode/delegated、OAuth 透传、token audience 绑定） | 第 2 个租户 / 端用户 OAuth 到下游 |
| 完整 effect/security/runtime 元数据（data_classification、retry、circuit breaker、并发/费用预算） | 接入外部 API / 写工具 |
| 间接注入全套（DLP、egress、injection eval gate、MCP 签名/registry/version-lock） | 开始吃**不可信外部源**（GitHub/wiki/外部 MCP） |
| 动态工具检索（RAG-MCP 式，对描述检索） | 某 bot 工具/分区数破 ~25–30 或路由准确率/预算不达标 |
| swagger 导入 → minify→聚类→重塑→review | 接入无 BAU 式现成工具层的第 2 个 app |
| spec-diff → 受影响工具/卡片反查（oasdiff 引擎） | spec 会变更且需自动同步时 |
| SSE 断线恢复（`id:`/`Last-Event-ID`/重放） | 长任务 / 弱网真实用户 |
| 第二 app 的 contract fixture（脱敏 OpenAPI + 不同 RBAC + 写例 + per-row 例 + 契约测试） | 准备冻结契约（v1beta）前——用于防 BAU-overfit |
| Studio 前端（表单 + chatbot 引导 + diff/eval 面板） | 契约稳定、≥2 app 跑通后 |
| 多租户隔离、OTel、LiteLLM 成本/限流、自检自改闭环（§12.4） | 平台化/规模化阶段 |

> 触发到来前，这些**只保留字段/规则形状**（§4），不建实现。

---

## 9. MVP 不做清单（明确非目标）

- ❌ 不接第二个 app、不做 swagger 导入。
- ❌ 不做 Studio 前端。
- ❌ 不做多租户/OAuth 委托/动态工具检索/spec-diff/断线恢复。
- ❌ 不冻结 `v1`（停在 `v1alpha1`）。
- ❌ 不吃不可信外部源（MVP 只吃 BAU 自有、且卡片人工审核）。

---

## 10. 精简路线图

| 阶段 | 内容 | 验收 |
|---|---|---|
| **P0** | 定 v1alpha1 契约形状（§5 红线 + §6 envelope + §4 字段/主键/身份形状） | 形状 + 规则评审通过；**不建机器** |
| **P1** | agent_core + DataScope + 读安全 + BAU 现有写 + **BAU 行为等价** + 最小 eval gate | BAU 回归全过、per-row 越权测试过、eval gate 生效 |

P2 及以后 = §8 附录各项按触发条件解锁。

---

## 11. 与完整设计的关系

本文是 [PLATFORM_DESIGN.md](./PLATFORM_DESIGN.md) 的**近期可执行子集**。完整设计不变、作为终态参照；本文每推进一项 §8 deferred，就回填完整设计对应章节。两份并存：**MVP 指导现在做什么，完整设计守住方向不跑偏。**
