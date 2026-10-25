"""Conservative character knowledge and explicit causal graph validation."""
def alias_map(entities):
    result={}
    for entity in entities:
        for name in [entity['name'],*entity.get('aliases',[])]:
            key=name.strip().casefold()
            if key in result and result[key]!=entity['name']:raise ValueError('别名同时指向多个人物，请先消歧：'+name)
            result[key]=entity['name']
    return result

def knowledge_view(facts,*,chapter_number,persona='',entities=()):
    names=alias_map(entities)
    normalize=lambda name:names.get(name.strip().casefold(),name.strip())
    persona=normalize(persona);visible=[];withheld=0
    for fact in facts:
        if fact['valid_from']>=chapter_number or (fact.get('valid_until') is not None and fact['valid_until']<chapter_number):continue
        if fact.get('review_status')=='rejected':continue
        item={**fact,'subject':normalize(fact['subject']),'holder':normalize(fact.get('holder','')),'known_by':[normalize(n) for n in fact.get('known_by',[])]}
        if persona and not (item.get('public') or persona in item['known_by'] or (item['kind']=='belief' and item['holder']==persona)):
            withheld+=1;continue
        item['authority']='author-confirmed' if item.get('review_status')=='confirmed' else 'derived-candidate'
        visible.append(item)
    return {'persona':persona,'facts':visible,'withheld':withheld,'policy':'信念/传闻不等于客观事实；未知不等于不存在；未授权的秘密不得变成人物知识。'}

def validate_causes(target_id,causes,existing):
    graph={r['id']:r.get('causes',[]) for r in existing};allowed=set(graph)
    if target_id in causes or any(cid not in allowed for cid in causes):raise ValueError('因果依据必须是本作品已有事实，且不能引用自己')
    graph[target_id]=causes;active=set();done=set()
    def visit(node):
        if node in active:raise ValueError('因果关系形成循环，请重新核对')
        if node in done:return
        active.add(node)
        for edge in graph.get(node,[]):visit(edge)
        active.remove(node);done.add(node)
    visit(target_id)
