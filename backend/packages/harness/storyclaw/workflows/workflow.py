"""Pure author-confirmation and continuity policies; no transport or persistence."""
import hashlib
import json

def outline_hash(content):
    from storyclaw.workflows.serial import framework_content
    from storyclaw.workflows.serial import digest
    return digest(framework_content(content))

def is_confirmed(content):
    return bool(content.get('volumes')) and content.get('_review',{}).get('hash')==outline_hash(content)

def pending_history(chapters):
    return [c['number'] for c in chapters if c.get('word_count',0)>0 and c.get('rag_status')!='loaded']
