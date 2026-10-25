"""Stable non-sensitive failure classification for every creative node."""
def model_failure(exc):
    status=getattr(exc,'status_code',None);body=getattr(exc,'body',None) or {};code=None
    if isinstance(body,dict):code=(body.get('error') or body).get('code')
    if status==429 and str(code) in ('1113','insufficient_quota'):
        return {'error_code':'supplier_quota','error':'模型供应商余额或资源包不足，已停止；请补充供应商额度后显式重试。'}
    if status==429:return {'error_code':'supplier_rate_limit','error':'模型供应商限流，已停止；请稍后核对并显式重试。'}
    if status in (401,403):return {'error_code':'supplier_auth','error':'模型供应商鉴权失败，请由运营检查配置。'}
    if status in (402,409):return {'error_code':'execution_blocked','error':'预算不足、计划已暂停或依赖已变化，已停止新的调用。'}
    return {'error_code':'model_interrupted','error':'模型调用中断，结果未完整采用；请核对候选和用量后再决定是否重试。'}
