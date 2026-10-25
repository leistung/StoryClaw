# reading-config-gen

> triggers: 阅读配置 / 阅读设置 / 阅读模板 / 生成阅读配置

## Description

阅读配置生成：根据用户偏好与阅读场景，生成个性化阅读配置 JSON。
用于新用户首次进入阅读页的默认配置、场景化配置推荐（夜间/护眼/沉浸）。

## Parameters

- `scene` (str, default="default"): default | night | eye_care | immersive | outdoor
  - default: 日间默认
  - night: 夜间暗色
  - eye_care: 护眼模式（低对比度）
  - immersive: 沉浸阅读（宽边距+大字）
  - outdoor: 户外强光（高对比度）
- `user_prefs` (dict, optional): 用户偏好 {"font_size":"large","background":"warm"}
- `book_genre` (str, optional): 书籍类型（影响推荐配色）
- `model_choice` (dict)

## Workflow

1. 解析场景与用户偏好
2. 构造 prompt：场景 + 偏好 + 配置字段约束
3. LLM 生成配置 JSON（字号/边距/背景/字色/亮度/行距/字体）
4. 返回标准配置 JSON

## Output

- `config_json` (str): 阅读配置 JSON 字符串，字段：
  ```json
  {
    "font_size": 18,
    "font_family": "serif",
    "line_height": 1.8,
    "margin": "medium",
    "background": "#faf8f5",
    "text_color": "#333333",
    "brightness": 0.9
  }
  ```
- `scene` (str): 实际应用场景
- `token_usage` (dict)

## Constraints

- 字号 14-24px，行距 1.4-2.2
- 夜间模式背景色亮度 < 15%，字色亮度 > 60%
- 护眼模式背景偏暖（色温 < 4000K 等效）
- 户外模式对比度 > 7:1（WCAG AAA）
- 输出必须是合法 JSON，可直接解析
