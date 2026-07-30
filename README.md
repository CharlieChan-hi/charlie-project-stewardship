# Charlie Project Stewardship

[![CI](https://github.com/CharlieChan-hi/charlie-project-stewardship/actions/workflows/ci.yml/badge.svg)](https://github.com/CharlieChan-hi/charlie-project-stewardship/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-F74D7B.svg)](LICENSE)

> A lightweight, repository-local stewardship harness for capable coding agents—durable context and evidence-based feedback without a mandatory workflow.

Charlie Project Stewardship 是一个以 Codex 为主要宿主的轻量项目治理插件。它不替模型规定“先做什么、后做什么”，而是把长期项目中最容易丢失的五类信息——**任务边界、项目地图、长期规则、跨会话进度和完成证据**——变成可检查、可恢复的项目资产。

核心原则：约束真实事实、授权边界和完成证据，不约束模型的推理方式与实现路线。五个核心能力按需独立触发，普通编码任务不需要经过固定流程。

## 它解决什么

模型越来越擅长写代码，但长期项目仍会反复遇到几类与“聪明程度”无关的问题：

- 复杂任务在执行中发生范围、事实源或验收标准漂移；
- 进入陌生仓库时缺少可信、精简的项目地图；
- 已确认的规则和失败经验随着会话结束而丢失；
- 长任务中断后无法准确恢复到最后一个可靠状态；
- “看起来完成”与“已有足够运行证据”被混为一谈。

本插件只为这些连续性问题提供最小治理层，不接管宿主 Agent 的实现判断。它由 5 个核心 Skill、6 个兼容入口、一组只使用 Python 标准库的确定性工具，以及行为、安全、幂等和漂移测试组成。

## 适合谁

- 长期维护同一仓库，并经常跨会话、设备或 Agent 工作；
- 希望项目知识保存在仓库，而不是只存在聊天记录中；
- 需要明确授权边界、事实来源和完成证据；
- 希望获得可审计、无外部服务依赖的本地工具；
- 不想用一套固定流程限制能力更强的模型。

它不适合一次性问答、很小且边界清楚的普通修改，也不提供工单看板、排期、依赖图、团队仪表盘或云同步。

## 五个核心能力

| Skill | 何时使用 | 主要产物 | 默认写入 |
|:---|:---|:---|:---|
| `task-contract` | 事实/来源冲突、验收不清、需分批审阅或任务边界尚未明确 | 目标、范围、事实源、非目标、验收证据和停止条件 | 否，默认留在对话中 |
| `project-bootstrap` | 明确要求初始化或接手仓库 | 最小项目地图，或非覆盖式创建建议 | 否，先检查或预览 |
| `project-memory` | 明确要求保存已确认、未来仍有用的知识 | 带范围、证据和失效条件的项目规则 | 是，但必须明确要求 |
| `plan-relay` | 明确要求跨会话、崩溃或设备恢复长任务 | 带稳定计划与步骤 ID 的仓库内状态 | 是；跨设备还需另行授权 Git 同步 |
| `project-health` | 明确要求项目审计或交付复验 | 区分已确认问题、启发式信号和未验证面的结论 | 否，默认只读 |

新用户只需关注这五个 Skill。`start-here`、`project-intake`、`project-scaffold`、`architecture-audit`、`completion-guard` 和 `capability-routing` 是旧版本兼容入口，不代表额外的强制流程。

### 它们如何协作

五个能力不是一条必须执行的流水线：

- 接手或初始化项目时，可使用一次 `project-bootstrap`；
- 当前任务存在实质歧义时，使用 `task-contract`；
- 只有任务确实需要中断恢复时，才使用 `plan-relay`；
- 只有知识已经确认且用户明确要求长期保存时，才使用 `project-memory`；
- 只有明确要求审计或交付复验时，才使用 `project-health`。

简单任务由宿主 Agent 正常完成，不会因为缺少治理文档而被阻塞。

## 它不是什么

这是一个 stewardship layer，不是工作流引擎、项目操作系统或任务管理器。它不规定阶段、角色和 Agent 编排，也不会强制规划、TDD、审查或发布流水线。

它不依赖或安装重型项目编排系统，也不内置浏览器自动化、语义代码索引、输出压缩器或外部任务数据库。宿主已经提供且当前任务确实需要的专用能力可以按需使用；插件不会为了“补全工具栈”隐式安装它们。

## 安装

要求：带 `plugin` 命令的当前 Codex、Git，以及运行确定性工具所需的 Python 3.9 或更高版本。运行时仅使用 Python 标准库。

将 GitHub 仓库添加为 marketplace，然后安装插件：

```bash
codex plugin marketplace add CharlieChan-hi/charlie-project-stewardship --ref main
codex plugin add charlie-project-stewardship@charlie-project-stewardship --json
```

安装后请新建一个 Codex 任务，使 Skill 和 metadata 从干净上下文加载。如需同时在 Claude Code 中使用，见"Claude 集成"一节。将来更新：

```bash
codex plugin marketplace upgrade charlie-project-stewardship --json
codex plugin add charlie-project-stewardship@charlie-project-stewardship --json
```

添加 marketplace 只让这个 Git 源可被当前 Codex 使用；它不会把插件发布进 OpenAI 官方 Plugins Directory。官方目录发布是单独的审核流程。

## Claude 集成

Codex 通过 plugin 机制原生加载本插件；Claude Code 通过 `CLAUDE.md` 获得等效的项目上下文和能力路由。

**在已安装本插件的项目中启用 Claude 支持：**

`project-bootstrap` 的最小模式会同时生成 `AGENTS.md`（Codex 自动读取）和 `CLAUDE.md`（Claude Code 自动读取），内容对等。若只需 Claude.md：

```bash
python3 "$PLUGIN_ROOT/shared/scripts/project_steward_scaffold.py" \
  --project-root "$PROJECT_ROOT" --minimal
```

预览无误后加 `--write`。生成后，Claude Code 在该项目下工作时会自动加载 `CLAUDE.md`，不需要额外配置。

**在 Claude Code 中调用 Skill：**

能力按名字调用——说"使用 task-contract"或"运行 project-health"即可。完整触发规则和执行边界见对应 `skills/<name>/SKILL.md`；Claude Code 直接读取 SKILL.md，无需 Codex 插件格式。

**本插件 repo 自身的 Claude 上下文：** 插件根目录的 `CLAUDE.md` 包含完整的目录地图和能力路由表，工作在本插件时由 Claude Code 自动加载。

## 60 秒快速体验

安装后，新建一个 Codex 任务并尝试以下任一提示：

```text
使用 $project-health 对当前仓库做只读健康审查。
先给结论，区分已确认问题、启发式信号和未验证面，不写文件。
```

```text
使用 $task-contract 把这个事实源冲突或验收不清的请求整理成最小任务契约，
明确目标、范围、事实源、非目标、验收证据和停止条件，不写文件。
```

```text
使用 $project-bootstrap 检查当前仓库，并预览它真正缺少的最小项目地图。
保留已有文件，不执行写入。
```

只有确实需要长期状态时，再明确调用：

- `使用 $project-memory 保存这条已经确认的项目规则……`
- `使用 $plan-relay 把这个长任务保存为可跨会话恢复的计划……`

这两项会改变仓库状态；Git commit、push、部署、发布和权限变化始终是独立授权边界。

## 安全与平台边界

- 只读意图优先；持久化能力只有在明确写入请求下才工作。
- 现有项目文件默认不覆盖；有差异时只报告，或在明确要求下生成采用计划。
- 不读取 `.env`、`.npmrc`、`.pypirc` 等 secret-capable 文件内容；审计只看必要的文件名与 Git ignore/tracking 元数据。
- 所有公开 CLI 在参数解析前检查高置信 secret，拒绝回显或复制命中的载体。
- POSIX 写入使用 project-root 锚定、symlink 拒绝、冲突令牌、原子替换和项目级锁。Windows／non-dirfd 环境目前只提供经过路径与 identity 检查的只读审计；插件自己的持久写入、删除和归档会 fail closed。
- 文件长度、通用命名和控制流密度只是调查线索，不是自动重构或完成阻塞。

实现细节见 [`docs/architecture.md`](docs/architecture.md)；设计依据与来源分级见 [`shared/references/project-operating-system.md`](shared/references/project-operating-system.md)。

## 直接使用确定性工具

每个脚本都支持 `--help`。以下命令从插件源码根目录运行，不带 `--write` 的检查或预览不会写目标项目：

```bash
PLUGIN_ROOT="$PWD"
PROJECT_ROOT="${PROJECT_ROOT:?Set PROJECT_ROOT to the target project}"

# 只读健康检查
python3 "$PLUGIN_ROOT/shared/scripts/project_steward_audit.py" \
  --project-root "$PROJECT_ROOT" --format json

# 预览最小项目地图；确认后再追加 --write
python3 "$PLUGIN_ROOT/shared/scripts/project_steward_scaffold.py" \
  --project-root "$PROJECT_ROOT" --minimal

# 查看或恢复持久计划
python3 "$PLUGIN_ROOT/shared/scripts/project_steward_plan.py" \
  --project-root "$PROJECT_ROOT" --machine workstation status

# 用真实变更面和验证证据做完成检查
python3 "$PLUGIN_ROOT/shared/scripts/project_steward_guard.py" \
  --project-root "$PROJECT_ROOT" \
  --changed-path src/example.py \
  --require-validation tests --validation-result tests=pass \
  --acceptance-status not-required
```

完整参数与写入约束以对应 Skill 和 `--help` 为准，不建议从 README 复制长参数后跳过事实核对。

## 开发与验证

基础回归不依赖第三方 Python 包：

```bash
python3 -m compileall -q shared/scripts tests
python3 -m unittest discover -s tests -v
```

在 Codex 开发环境中，完整门禁还会验证全部 Skill、插件 manifest 和 CLI forward checks：

```bash
python3 shared/scripts/validate_stewardship_plugin.py
```

维护已配置的本地开发副本时，所有门禁通过后再刷新 cachebuster。下面这组命令只适用于默认 personal marketplace；运行前先确认它的 entry 指向当前 checkout：

```bash
python3 shared/scripts/validate_stewardship_plugin.py --update-cachebuster
MARKETPLACE_NAME="$(
  python3 "${CODEX_HOME:-$HOME/.codex}/skills/.system/plugin-creator/scripts/read_marketplace_name.py"
)"
codex plugin add "charlie-project-stewardship@$MARKETPLACE_NAME" --json
```

如果当前 checkout 来自非默认本地 marketplace，必须读取那一份 marketplace 文件的名称，并用 `codex plugin list --json` 核对其 source 后再重装：

```bash
MARKETPLACE_ROOT="${MARKETPLACE_ROOT:?Set MARKETPLACE_ROOT to the marketplace root}"
MARKETPLACE_PATH="$MARKETPLACE_ROOT/.agents/plugins/marketplace.json"
MARKETPLACE_NAME="$(
  python3 "${CODEX_HOME:-$HOME/.codex}/skills/.system/plugin-creator/scripts/read_marketplace_name.py" \
    --marketplace-path "$MARKETPLACE_PATH"
)"
codex plugin list --json
codex plugin add "charlie-project-stewardship@$MARKETPLACE_NAME" --json
```

若 list 中该 marketplace 的插件 source 不是当前 checkout，先停止并修正来源，不要重装另一份同名源码。不要手改插件缓存、`config.toml` 或 marketplace 安装状态。贡献说明见 [`CONTRIBUTING.md`](CONTRIBUTING.md)，安全问题报告方式见 [`SECURITY.md`](SECURITY.md)。

## 兼容性与设计立场

- Codex 是 plugin 宿主；Claude Code 通过 `CLAUDE.md` 获得等效上下文和能力路由，两者共享同一组 SKILL.md 作为事实源。`.claude-plugin/plugin.json` 是可移植 package metadata，不会修改任何活动 Claude 配置。
- 插件面向具备自主规划和工具调用能力的现代 coding Agent，不把某个模型 ID 写成硬依赖。兼容性由行为、权限、文件系统能力和实际门禁决定。
- 外部项目只作为设计灵感或可选能力示例，不是依赖、捆绑组件或官方背书。

## License

[MIT](LICENSE) © 2026 Charlie
