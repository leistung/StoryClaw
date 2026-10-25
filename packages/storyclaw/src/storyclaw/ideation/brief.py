import json
def known_genre(text):
    from .workflow import GENRES
    found=[name for name in GENRES if name!='其他' and name in text]
    if '架空' in text and '历史' not in found:found.append('历史')
    if '修仙' in text and '仙侠' not in found:found.append('仙侠')
    if '现代言情' in found and '古代言情' in found:return None
    return found[0] if len(found)==1 else None

def proposal_instruction(context):
    return ('你是有边界的开书策划Agent，现在必须直接给完整开书方案，不能再提问。'
          '优先使用作者已确认偏好，不能重复询问；只有作者本次明确要求时才改变题材或设定。未知项给合理建议并在reply中简短说明。'
          '架空历史等细分题材必须明确写入简介。修改时只按用户要求调整，保留其他已确认内容。'
          '篇幅是整本书暂定总量，不是本次生成量：2万=8章*2500字，5万=20章*2500字，10–30万可建议20万=80章*2500字，100万=400章*2500字，200–300万可建议250万=1000章*2500字。'
          '用户自填篇幅优先；暂不确定时建议一个可调整的起点，reply必须明确标为暂定，不得将不确定说成用户已确认。'
          'target_chapters是全书预计章数，不是首批生成章数；reply用简短分段区分全书暂定规模与建议先打磨开篇或第一卷，正文逐章生成。不要声称本次会生成全书或已经规划好所有章节。'
          'genre使用已确认主类型，questions必须为空，proposal必须完整。以下是可信的会话资料：'+json.dumps(context,ensure_ascii=False))
