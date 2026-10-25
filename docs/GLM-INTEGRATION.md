# 智谱模型接入

当前平台配置：

- 协议：OpenAI Chat Completions 兼容。
- API Base URL：https://open.bigmodel.cn/api/paas/v4。
- 默认文本模型：glm-5.1，思考模式 disabled（减少短交互等待），上下文上限配置 200000。
- 向量模型：embedding-3，显式请求 dimensions=1024，与当前 Milvus 维度一致。
- 密钥通过中台配置接口加密存入 PostgreSQL，不写入本文件、源码或默认 YAML。
- 其他目录中的演示文本模型暂时禁用，避免选择未配置密钥的模型。

## 积分

GLM-5.1 暂采用开发测试积分价：每千输入 Token 1 积分、每千输出 Token 1 积分；按现有系统规则取整。
这是平台开发积分规则，不是智谱的人民币 API 单价，正式运营前需在中台制定计费策略。
Embedding 调用消耗智谱账户用量，目前尚未单独实现向量费用的用户积分结算。

## 验证

真实接口短测：glm-5.1 返回 HTTP 200 和文本；embedding-3 返回 HTTP 200 和 1024 维向量。
另通过项目实际 LangChain 流式客户端与 Embedding 服务验证。
自动化用例覆盖请求维度传递、响应数量和维度校验、思考模式参数传递与其他提供商参数不受影响。
本次没有进行整本小说生成的质量评测，也不将接口连通等同于已证明长篇一致性。

## 官方文档

- https://docs.bigmodel.cn/cn/guide/models/text/glm-5.1
- https://docs.bigmodel.cn/cn/guide/models/embedding/embedding-3
- https://docs.bigmodel.cn/cn/guide/start/pricing
