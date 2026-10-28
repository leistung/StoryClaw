"""Version-bound setting edits, shared by agent proposals and author adoption."""
from storyclaw.workflows.serial import digest

def setting_data(entity):
    return {k:getattr(entity,k) for k in ('id','entity_type','name','category','description','extra_json')}

def setting_hash(entity):return digest(setting_data(entity))
