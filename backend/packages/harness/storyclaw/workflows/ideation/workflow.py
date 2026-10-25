"""A bounded LangGraph director. Choice tools are deterministic; drafting uses the model.

Two grouped interviews, then proposal/revision. No autonomous question loop or book creation.
"""
from typing import TypedDict,Any
from langgraph.graph import StateGraph,START,END

CATALOG=[
 ('玄幻',['东方玄幻','传统玄幻','玄幻脑洞','高武世界'],['少年成长','家族传人','底层小人物','反派视角'],['修炼成长','家族兴衰','世界秘密','群像争霸']),
 ('仙侠',['古典仙侠','修真成长','凡人修仙','仙侠日常'],['凡人少年','宗门弟子','散修','女修'],['修仙求道','宗门纷争','情义取舍','逆天改命']),
 ('历史',['架空历史','真实朝代','历史脑洞','历史种田'],['平民百姓','小官吏','将士','经营者'],['乱世求生','朝堂权谋','种田经营','家国变革']),
 ('都市',['都市日常','都市脑洞','都市异能','职场商战'],['普通职员','小店经营者','学生','家庭成员'],['事业逆袭','守护家庭','生活选择','秘密调查']),
 ('科幻',['星际未来','近未来科技','人工智能','时间探索'],['工程师','普通居民','探索者','人工智能'],['文明危机','科技代价','探索未知','身份与记忆']),
 ('末世',['灾变求生','废土重建','末日危机','生存经营'],['普通幸存者','家庭成员','救援人员','群像团队'],['生存资源','守护家人','重建秩序','灾难真相']),
 ('悬疑',['悬疑推理','悬疑脑洞','民俗悬疑','心理悬疑'],['普通目击者','调查者','受害者家属','小镇居民'],['追查真相','失踪之谜','身份秘密','人性选择']),
 ('奇幻',['西方奇幻','异世界冒险','魔法世界','史诗奇幻'],['小人物','冒险者','魔法学徒','非人角色'],['探索冒险','种族纷争','魔法代价','文明变迁']),
 ('武侠',['传统武侠','江湖成长','武侠悬疑','新派武侠'],['江湖新人','游侠','普通百姓','隐退高手'],['侠义抉择','江湖恩怨','追查秘密','守护苍生']),
 ('古代言情',['宫斗宅斗','古风世情','种田经营','古言脑洞'],['普通女子','世家子女','市井经营者','独立谋生者'],['情感选择','家庭纷争','自我成长','经营生活']),
 ('现代言情',['职场婚恋','青春甜宠','现言脑洞','年代情感'],['职场新人','普通女性','学生','家庭成员'],['情感成长','事业与爱情','家庭选择','自我实现']),
 ('现实',['家庭生活','乡土乡村','时代变迁','社会成长'],['普通劳动者','家庭成员','小镇青年','群像人物'],['生活困境','家庭关系','命运变迁','个人选择']),
 ('游戏体育',['游戏竞技','体育竞技','虚拟世界','电竞成长'],['新人选手','退役者','教练','普通玩家'],['竞技成长','团队协作','职业转折','规则秘密']),
 ('军事',['历史军事','谍战悬疑','军旅成长','架空战争'],['基层士兵','军官','情报人员','普通平民'],['战场求生','情报博弈','团队成长','家国抉择']),
 ('轻小说',['青春校园','日常幻想','异世界冒险','轻松群像'],['普通学生','新人冒险者','非人角色','群像人物'],['日常成长','朋友与羁绊','世界秘密','冒险探索']),
 ('诸天无限',['无限闯关','诸天冒险','规则试炼','多世界成长'],['普通参与者','团队新人','独行者','群像团队'],['规则解谜','生存挑战','团队选择','世界真相']),
 ('其他',['青春校园','轻小说风格','跨类型融合','由AI建议'],['普通人','成长中的少年','群像人物','由AI建议'],['成长与选择','冒险与探索','家庭与情感','由AI建议']),
]
GENRES=[row[0] for row in CATALOG]

def question(key,title,options,description=''):return {'id':key,'question':title,'options':options,'multiple':False,'description':description}
def preferences(genre=None):
    result=[]
    if not genre:result.append(question('genre','这本书首先选择什么题材？',GENRES))
    result.extend([question('tone','你希望读者获得怎样的阅读感受？',['热血爽快','温暖治愈','悬疑紧张','沉静写实','由AI建议']),question('length','整本书预计写多少字？',['短篇故事（约2万字）','中篇故事（约5万字）','长篇小说（约10–30万字）','长篇连载（约100万字）','超长连载（约200–300万字）','暂不确定，先探索故事'], '这是全书的暂定规模，用于估算章数和故事节奏，不是本次生成量，也不是字数上限。可以随时调整；其他目标请写在下方。正文在创作台按章节生成，建议先打磨开篇或第一卷。')])
    return result

def story(genre):
    row=next((r for r in CATALOG if r[0]==genre),CATALOG[-1])
    return [question('subgenre','在这个题材里，更想写哪个方向？',row[1]),question('protagonist','故事主要跟随怎样的主角？',row[2]+['由AI建议']),question('conflict','最想围绕什么核心冲突展开？',row[3]+['由AI建议'])]

class DirectorState(TypedDict,total=False):
    mode:str
    round:int
    genre:str
    has_proposal:bool
    action:str
    questions:list[dict]
    reply:str
    draft_tool:Any
    result:Any

def read_catalog(state):
    # Narrow suggestions from the selected genre, never re-ask unrelated interests.
    return {'genre':state.get('genre') or '其他'}
def decide(state):
    if state.get('mode') in ('proposal','revise') or state.get('has_proposal') or state.get('round',0)>=2:return {'action':'draft'}
    return {'action':'preferences' if state.get('round',0)==0 else 'story'}
def ask_preferences(state):return {'questions':preferences(None if state['genre']=='其他' else state['genre']),'reply':'先集中确认题材、阅读感受和篇幅。接下来只再补一轮关键设定，就给你开书方案。'}
def ask_story(state):return {'questions':story(state['genre']),'reply':f'接下来只补齐「{state["genre"]}」的细分方向、主角与核心冲突。这是最后一轮选项，确认后直接生成方案；不确定的可以交给我建议。'}
async def draft(state):return {'result':await state['draft_tool'](),'questions':[]}

graph=StateGraph(DirectorState)
graph.add_node('catalog_tool',read_catalog);graph.add_node('director',decide)
graph.add_node('preferences',ask_preferences);graph.add_node('story',ask_story);graph.add_node('draft',draft)
graph.add_edge(START,'catalog_tool');graph.add_edge('catalog_tool','director')
graph.add_conditional_edges('director',lambda state:state['action'],{'preferences':'preferences','story':'story','draft':'draft'})
for node in ('preferences','story','draft'):graph.add_edge(node,END)
ideation_graph=graph.compile()
