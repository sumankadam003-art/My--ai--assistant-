# Neha Action Intelligence — Architecture and Implementation Plan

**Status:** Design baseline; implementation not yet started  
**Audited branch:** `feature/conversational-action-chat`  
**Design principle:** One conversational interface, one dedicated action-planning brain, many trusted capabilities.

## 1. Goal

Neha should accept ordinary natural-language requests through the same chat interface used for conversation. A dedicated Action AI should determine whether a message is conversational, informational/research-oriented, a single action, or a multi-step task. For tasks, it should create a bounded plan, select registered capabilities, ask for missing information, obtain explicit approval where required, execute through trusted application code, and report verified results.

The goal is broad capability through an extensible tool ecosystem—not an unsafe promise of unlimited actions. Neha can only perform tasks supported by registered tools, platform APIs, permissions, and connected services.

## 2. Findings from the current repository

The following findings are based on the audited files in this branch:

| Existing module | Current responsibility | Design implication |
|---|---|---|
| `src/neha_gateway.py` | Main conversational provider fallback (Groq then Gemini), history and local/cloud memory context | Keep this as the conversation gateway; do not overload it with action execution |
| `src/intent_interpreter.py` | Groq-based classifier with a fixed allowlist of 10 action names | Replace its fixed-command role with structured planning; preserve a compatibility adapter during migration |
| `src/action_registry.py` | Registers 13 built-in action names and mobile URL mappings | Reuse as the initial trusted capability source; enrich its metadata |
| `src/plugin_manager.py` | In-memory registry of trusted Python handlers; does not load arbitrary plugin files | Extend registry metadata, not arbitrary code loading |
| `src/action_engine.py` | Central action registry, permission checks, risk levels, approval gate, audit events, emergency stop | Reuse as the execution policy boundary |
| `src/action_service_factory.py`, `src/authorized_action_service.py`, `src/action_authorization.py` | Owner authentication, exact permission allowlist, one-time argument-bound approvals | Keep these controls authoritative; model output must never grant approval |
| `src/action_engine_bridge.py` | Adapts registered plugins into the ActionEngine | Reuse, then extend to support typed argument schemas and capability metadata |
| `src/action_audit.py` | Append-only metadata audit log; excludes prompts, arguments, and secrets | Preserve privacy-conscious audit behaviour |
| `src/app_api.py` | Authenticated chat endpoint; currently calls the fixed interpreter, asks yes/no for an action, or falls back to conversation | Make this the API entry to an orchestration service, not the planner itself |
| `src/actions.py` | Executes selected Termux/Android commands and app-opening operations | Treat every handler as trusted code; never pass model-generated shell strings to it |
| `neha-mobile/src/app/index.tsx` | Single chat UI, sends recent history, handles approved mobile URL handoff; several dashboard tiles and voice controls are placeholders | Keep chat as the primary interface; later remove dependence on a separate quick-action menu |

### Current limitations confirmed by inspection

- The interpreter accepts only 10 exact action identifiers and returns either `chat` or one `action`.
- The current chat action path handles an action name with empty arguments. It cannot yet collect arbitrary parameters or build multi-step plans.
- The existing plugin registry has no formal input/output schema for tools.
- The action engine executes only trusted registered Python handlers. This is a security strength, not a limitation to remove.
- The inspected backend has no dedicated web-search/research adapter wired into the orchestration path.
- The existing chat gateway and Action AI currently share the same general provider modules; a separate Action AI provider configuration does not yet exist.
- The existing SMS path has argument validation and an Android SMS composer handoff. The new planner must preserve that human-reviewed composer flow rather than sending SMS silently.

## 3. Target architecture

```text
User message + recent conversation
              |
              v
      Neha Chat API / Session
              |
              v
    Request Orchestrator
              |
       +------+------+
       |             |
       v             v
Conversation     Action Intelligence
Gateway          Brain (dedicated AI)
(memory/chat)    (intent + planning)
                      |
                      v
              Structured Task Plan
                      |
                      v
              Plan Validator
              - known tool IDs only
              - schema validation
              - step/dependency limits
              - risk classification
                      |
                      v
              Tool / Capability Registry
              - device actions
              - app intents / URLs
              - SMS composer
              - research/search
              - future integrations
                      |
                      v
              Approval & Permission Gate
                      |
                      v
              Trusted Action Executor
                      |
                      v
              Result / Verification Layer
                      |
                      v
               Neha's chat response
```

The Action Intelligence Brain proposes structured intent and plans. It does not receive direct shell, filesystem, unrestricted network, or credential access. Trusted Python/Android adapters perform operations after validation.

## 4. Core components

### 4.1 Request Orchestrator

A deterministic application service invoked for every chat message. It routes between:
- ordinary conversation → existing `NehaGateway`;
- information request → research capability, when appropriate;
- action request → Action AI planner;
- ambiguous request → ask a concise clarification question.

It should pass relevant conversation history and the user's current request, but must not treat old chat messages as fresh execution instructions.

### 4.2 Dedicated Action AI provider

Create a provider interface independent from `NehaGateway`, with configuration separate from normal conversation providers. The initial implementation should support the providers already present in the repository where technically compatible, with an explicit action-specific model/provider setting and a safe fallback policy.

The Action AI should return machine-validated structured data, not prose interpreted as commands. Its output contract should represent:
- route: conversation, research, action, or clarification;
- user goal in plain language;
- ordered steps with registered tool IDs and JSON arguments;
- dependencies between steps;
- missing required fields/questions;
- expected result for each step;
- risk/approval rationale.

The model's claimed risk level is advisory only. The application computes the authoritative risk from trusted tool metadata.

### 4.3 Capability registry

Each trusted capability should declare:
- stable tool ID and human-readable description;
- supported platform(s);
- typed input schema and required/optional fields;
- output schema;
- required permission(s);
- risk level;
- whether owner confirmation is always required;
- whether it is read-only, reversible, or externally consequential;
- timeout and idempotency characteristics.

Only application-maintained, reviewed adapters may register executable handlers. AI can select from registered capabilities but cannot install, import, or execute arbitrary code. Adding a capability should mean adding and testing a trusted adapter plus metadata—not changing the planner's prompt with another hardcoded phrase.

### 4.4 Research capability

Add a dedicated search/retrieval adapter for web research. It should return source URLs, titles, snippets/content, retrieval timestamps, and errors in a structured result.

Research content is untrusted data. Web pages, search snippets, documents, and tool outputs must never be treated as system instructions or permission grants. The Action AI may use researched facts to plan the next step, but the application validates every proposed tool call. Cite sources in user-facing research answers where available.

Research itself must not silently cause consequential external actions such as purchases, messages, account changes, or submissions.

### 4.5 Planner and bounded executor

The planner should support sequential plans with explicit dependencies. The first release should use sequential execution only; parallel branches can be considered after reliable sequential behaviour exists.

Initial guardrails:
- maximum 8 steps per plan;
- maximum 12 tool calls per user task, including replans;
- per-tool timeout and an overall task deadline;
- validate every step immediately before execution;
- stop on failed required dependencies;
- do not retry non-idempotent actions automatically;
- require a fresh approval if action arguments change;
- maintain a task ID and step-level status;
- allow cancellation and emergency stop;
- never report success merely because a handler returned text.

Limits are configuration constants, not model-controlled values.

### 4.6 Clarification and approvals

Neha should ask only for missing information needed by the next safe step. For parameterized tasks, collect and validate fields before presenting an approval summary.

Approval must bind to the exact action, exact arguments, authenticated owner, and short expiry. Any changed recipient, message body, destination, amount, or other consequential parameter invalidates the previous approval.

For SMS specifically:
1. identify and disambiguate the recipient;
2. collect the message text;
3. show the exact recipient and message;
4. require explicit owner confirmation;
5. open the existing Android SMS composer prefilled with those details;
6. let the owner press Send manually;
7. report only what the app can actually verify.

### 4.7 Result verification

Every tool result should distinguish:
- succeeded and independently verified;
- execution handed off but not verified;
- failed;
- blocked by permissions/approval;
- timed out or unknown.

The chat response must preserve that distinction. The current engine's `executed_unverified` status is a useful starting point.

## 5. Security rules (non-negotiable)

1. Never execute model-generated shell commands, Python, JavaScript, SQL, or arbitrary URLs directly.
2. Model output is a proposal, never an approval signal.
3. Validate tool IDs against the trusted registry and arguments against schemas.
4. Enforce owner authentication, exact permission allowlists, risk policy, and one-time approval receipts in application code.
5. Keep API keys and service-role credentials in the trusted backend only.
6. Treat web/search/document/tool output as untrusted data; defend against prompt injection.
7. Require explicit confirmation for externally consequential or destructive actions.
8. Use least privilege and deny by default when permission configuration is absent.
9. Audit action metadata without storing secrets, full message content, or sensitive arguments unnecessarily.
10. Provide cancellation and emergency stop; stop plans safely after failed prerequisites.

## 6. Suggested package boundaries

Names are proposed; inspect the repository for collisions before creating files.

- `src/request_orchestrator.py` — deterministic top-level route and orchestration entry.
- `src/action_ai/` — provider interface, provider adapters, prompt/structured-output contract.
- `src/task_planner.py` — plan parsing, validation, dependency graph and bounded plan state.
- `src/capability_registry.py` — stable metadata and lookup for trusted capabilities.
- `src/research_tools/` — search adapter and structured source results.
- `src/task_executor.py` — sequential execution, approvals, timeout, cancellation and result collection.
- Existing `action_engine.py`, `authorized_action_service.py`, `action_authorization.py`, and `action_audit.py` remain the enforcement foundation.

Do not create these files until an exact-path collision check and dependency audit are complete.

## 7. Phased implementation

### Phase 0 — Architecture and baseline audit
- Preserve current working behaviour and local uncommitted files.
- Record module responsibilities and data flow.
- Inventory all existing tools, permissions, schemas, and platform constraints.
- Confirm existing automated test commands and current CI baseline.

### Phase 1 — Typed capability registry
- Add structured input/output schemas and trusted capability metadata.
- Adapt existing registered actions without changing their observable behaviour.
- Add tests for unknown tools, invalid arguments, disabled tools, permissions, risk, and approval binding.

### Phase 2 — Dedicated Action AI
- Add separate provider configuration and a strict structured response contract.
- Parse and validate output; reject malformed, unknown, or unsafe tool proposals.
- Keep conversation provider configuration independent.

### Phase 3 — Request orchestration and clarification
- Route every chat message through a deterministic orchestrator.
- Use the existing conversation gateway for ordinary chat.
- Collect missing arguments through natural conversation and validate them.

### Phase 4 — Sequential multi-step task execution
- Add task state, dependencies, bounded loops, cancellation, retries only for safe idempotent operations, and truthful step results.
- Require approvals per consequential step or exact approved batch; never infer consent from AI output.

### Phase 5 — Research integration
- Add web search/retrieval as a read-only capability.
- Pass structured research results back to the planner as untrusted data.
- Cite research sources and prevent research results from authorizing actions.

### Phase 6 — Mobile integration and user experience
- Keep the single chat interface as the primary interface.
- Integrate SMS argument collection while preserving the existing SMS composer and manual Send action.
- Replace placeholder UI affordances only when their real integrations are ready.
- Test on the actual Android device; CI alone cannot verify Android intents or installed-app behaviour.

### Phase 7 — Reliability and expansion
- Add end-to-end tests for conversation, research, single actions, multi-step tasks, cancellations, expired approvals, provider failures, tool failures, and prompt-injection attempts.
- Add new trusted capabilities incrementally.
- Consider voice only after text orchestration is reliable.

## 8. Acceptance criteria

The architecture is ready for a first production-quality release when:
- every chat request is routed through the orchestrator;
- normal conversation still uses existing memory/provider behaviour;
- the Action AI can select any registered capability without a hardcoded phrase list;
- invalid or unknown tools and arguments are rejected safely;
- missing information triggers clarification rather than guessing;
- multi-step plans respect dependencies and execution limits;
- approvals are exact, owner-bound, short-lived, and single-use;
- SMS still requires review and manual Send in the Android composer;
- research results are source-backed and treated as untrusted;
- each step returns an honest status;
- regression tests and Android device tests pass.

## 9. Decisions to keep configurable

- Action AI provider and model;
- provider fallback order for action planning;
- maximum plan steps/tool calls and task deadline;
- risk thresholds and approval policy;
- research provider and allowed domains (if later required);
- per-tool timeout and retry policy.

## 10. Explicit non-goals

- No arbitrary shell/terminal execution generated by AI.
- No unrestricted plugin downloads or dynamic Python imports.
- No silent SMS, purchases, account changes, or destructive actions.
- No claim of unlimited capabilities.
- No replacement of the existing action security engine with model judgement.
- No broad rewrite of the working chat, authentication, memory, or SMS modules.

---

**Implementation status:** This file is a design baseline only. It does not claim that the Action Intelligence Brain, research adapter, typed tool schemas, or multi-step executor have been implemented. The existing conversational-action PR remains a narrow prototype/integration step and must be tested and reviewed separately.
