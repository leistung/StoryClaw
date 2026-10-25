import math

from app.services.platform.configs import load_pricing


def get_model_pricing(model_id: str) -> dict | None:
    return load_pricing().get("pricing", {}).get(model_id)


def _divisor() -> int:
    base = load_pricing().get("defaults", {}).get("price_base", "per_1k_tokens")
    return {"per_token": 1, "per_1k_tokens": 1000, "per_1m_tokens": 1_000_000}.get(base, 1000)


def compute_cost(model_id: str, in_tokens: int, out_tokens: int) -> int:
    """返回积分消耗(整数)。无 token 返回 0。"""
    m = get_model_pricing(model_id)
    if not m or not m.get("enabled", True):
        raise ValueError(f"模型 {model_id} 未配置有效积分价格")
    if not (in_tokens or out_tokens):
        return 0
    div = _divisor()
    cost = (in_tokens / div) * m["input_price"] + (out_tokens / div) * m["output_price"]
    return max(1, math.ceil(cost))
