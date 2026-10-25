# 真实模型评估与实验

这里保存会访问实际运行平台、可能产生模型费用的实验，不随 `make test` 自动执行。

- `cases/`：原创样书输入。
- `run.py`、`serial_smoke.py`：可恢复的逐章生成实验。
- `live_agent_acceptance.py`：通过后台计划进行有预算上限的真实验收。
- `quality.py`：字数、完整性及文本基础检查。
- `launch.py`、`status.py`：实验进程启动与状态查看。
- `runs/`：已有样书、任务回执、报告和中断候选；Git与Docker构建均忽略。迁移时保留全部119个原始输出文件，内容未改写。
- `legacy/`：较早的付费烟测脚本，接口可能过时，留作参考，不是当前测试入口。

当前测试边界见[开发测试手册](../../docs/10-开发测试与文档维护.md)；历史报告在 [实验文档](../../docs/archive/experiments/01-原小说实验说明.md)。恢复、修复样书等专项运维工具放在 `backend/scripts/samples/`，不会自动恢复暂停计划。

## 使用边界

实际生成需要已启动平台、有效模型配置和显式的预算/授权参数。先阅读脚本 `--help` 和对应文档；凭据通过环境变量传入，不能写入回执。脚本创建的是私密测试作品，不自动发布。

```bash
python3 backend/evaluations/serial_smoke.py --help
python3 backend/evaluations/live_agent_acceptance.py --help
```

仅验证代码请使用 `make test`。完整隔离数据库回归见 [测试说明](../tests/README.md)。
