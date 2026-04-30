# Python And uv Rules

## 目标

统一本项目的后端、脚本和测试开发方式，避免出现多套 Python 依赖管理方式并存的问题。

## 语言要求

- 后端服务默认使用 `Python`
- 数据初始化、知识库构建、离线处理、测试辅助脚本默认使用 `Python`
- 若已有前端目录使用 `TypeScript`，按现有前端技术栈维护，不要求强行迁移
- 除前端外，不新增其他语言的服务端主实现

## Python 版本

- 与项目 `pyproject.toml` 中声明的 Python 版本保持一致
- 新增语法或标准库能力前，先确认不会超出项目声明版本

## 依赖管理

- 统一使用 `uv`
- 常用命令：

```bash
uv sync
uv add <package>
uv remove <package>
uv run python -m app.scripts.<script_name>
uv run pytest
```

- 依赖变更必须落到 `pyproject.toml` 和锁文件
- 不在 README、脚本说明、Issue 处理说明里推广 `pip install`

## 运行约束

- 执行 Python 命令时优先使用 `uv run`
- 新增脚本时优先支持 `python -m package.module` 调用方式
- 新增开发文档时，命令示例优先写成 `uv` 风格

## 工程建议

- 优先使用标准库和现有依赖，避免重复引入近似能力包
- 保持模块职责单一，避免把配置、数据库访问、业务编排、输出格式化混在一个文件
- 对外提供的脚本应具备清晰参数、帮助信息和失败提示
