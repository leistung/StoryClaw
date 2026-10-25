"""Domain session transitions. The caller persists the returned state atomically."""
from .models import Turn,DiscussionOut
from .brief import known_genre,proposal_instruction
from .workflow import GENRES,ideation_graph

async def advance_discussion(state,data,infer,on_delta=None):
    saved=dict(state);history=list(saved.get('history',[]));answers=dict(saved.get('answers',{}))
    latest=data.messages[-1].content
    for answer in data.answers:
        answers[answer.id]='；'.join([*answer.values,answer.custom.strip()]).strip('；')
    genre=answers.get('genre') or saved.get('genre') or data.genre or known_genre(saved['brief']) or known_genre(latest)
    if genre and genre not in GENRES:genre=known_genre(genre) or '其他'
    if not history:
        history=[{'role':turn.role,'content':turn.content} for turn in data.messages]
    else:history.append({'role':'user','content':latest})
    async def draft_tool():
        context={'original_idea':saved['brief'][:1500],'confirmed_preferences':answers,'genre':genre,'discussion':[{**turn,'content':turn['content'][:500]} for turn in history[-6:]],'current_proposal':saved.get('proposal'),'revision_request':latest if saved.get('proposal') else None}
        instruction=proposal_instruction(context)
        transformed=data.model_copy(update={'guided':False,'mode':'proposal','messages':[Turn(role='user',content=instruction[:6000])]})
        return await infer(transformed)
    outcome=await ideation_graph.ainvoke({'round':saved.get('round',0),'mode':data.mode,'has_proposal':bool(saved.get('proposal')),'genre':genre,'draft_tool':draft_tool})
    if outcome['action']=='draft':
        result=outcome['result'];result.questions=[];result.stage='review'
    else:
        result=DiscussionOut(reply=outcome['reply'],questions=outcome['questions'],stage=outcome['action'])
        if on_delta:await on_delta(result.reply)
        saved['round']=saved.get('round',0)+1
    result.question_round=saved.get('round',0)
    history.append({'role':'assistant','content':result.reply})
    saved.update({'history':history[-16:],'answers':answers,'genre':genre,'proposal':result.proposal.model_dump() if result.proposal else saved.get('proposal')})
    return saved,result
