# AGENTS.md

## 适用范围

本文件适用于整个仓库：

- `/Users/bill/code/AI/NL2SQL/data-agent`
- `/Users/bill/code/AI/NL2SQL/data-agent-fronted`
- `/Users/bill/code/AI/NL2SQL/docs`
- `/Users/bill/code/AI/NL2SQL/scripts`

如子目录未来新增更细粒度的 `AGENTS.md`，则子目录文件优先。

## 项目定位

这是一个面向业务问数场景的 `NL2SQL` 项目工作区，包含：

- Python 后端 Agent 服务
- 数据初始化与知识库构建脚本
- 前端问答展示界面
- 文档、截图与辅助脚本

## 默认开发约束

### 1. 语言约束

- 后端服务、数据处理脚本、初始化脚本、测试脚本默认使用 `Python`
- 除前端现有 `Next.js / TypeScript` 工程外，不新增 `Node.js`、`Go`、`Java`、`Rust` 等后端实现作为主方案
- 如确需引入非 Python 语言，必须有明确理由，例如必须复用现有前端框架或第三方运行时要求

### 2. 依赖与运行约束

- Python 依赖统一使用 `uv` 管理
- 新增依赖时，优先更新 `pyproject.toml`
- 安装依赖、运行脚本、执行测试时，优先使用 `uv run`、`uv sync`、`uv add`
- 不要把 `pip install ...` 作为本项目标准用法写入文档

### 3. 注释与可读性约束

- 新增或修改的 Python 代码必须包含详细注释
- 复杂函数必须包含清晰的文档字符串，说明输入、输出、业务意图和关键约束
- 非显而易见的判断、检索逻辑、SQL 生成逻辑、时间解析逻辑、SSE 事件组装逻辑必须写行内注释
- 注释应解释“为什么这样做”和“业务含义”，不能只重复代码字面意思
- 对外接口、核心数据结构、关键流程节点必须保证阅读者不翻上下文也能理解

### 4. 变更边界

- 优先保持现有目录结构稳定
- 未经明确要求，不重命名公开接口
- 未经明确要求，不删除已有数据、截图、脚本和测试
- 任何影响问数链路行为的改动，都应补充验证

## 实施要求

### Python 代码

- 优先补充类型标注
- 优先写清楚函数职责，而不是把多个步骤堆在一个大函数里
- 涉及 Agent 节点时，节点输入、状态更新、输出、副作用都要能从注释看明白

### 文档

- 新增命令优先写成 `uv` 形式
- README、脚本说明、初始化说明应与实际运行方式一致

### 测试

- 修改后端逻辑时，优先补或更新 `pytest` 测试
- 如果无法测试，必须在变更说明里明确指出原因和风险

## 规则文档

详细规范见：

- `/Users/bill/code/AI/NL2SQL/rules/README.md`
- `/Users/bill/code/AI/NL2SQL/rules/python-uv.md`
- `/Users/bill/code/AI/NL2SQL/rules/commenting.md`
- `/Users/bill/code/AI/NL2SQL/rules/workflow.md`
