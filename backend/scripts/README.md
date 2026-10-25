# 后端开发与维护工具

- `check_docs.py`：现行文档链接、编号与Git忽略规则检查。
- `test.py`：统一离线及隔离数据库测试入口。
- `samples/`：已有样书的只读快照、候选恢复或显式修复。修复脚本可能调用付费模型，不能作为自动测试运行。

平台日常运维命令仍使用应用模块 `python -m app.admin_cli` 和 `python -m app.ops_cli`，保持鉴权、数据和计量实现只有一份。部署启动工具放在 `deploy/`，实际生成实验放在 `backend/evaluations/`。
