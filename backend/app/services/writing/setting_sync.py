"""Compatibility hook. Generated drafts never auto-overwrite author setting cards.

Confirmed-text indexing and explicit design adoption replace the former untracked
background LLM side effect. Kept so older integrations can call launch safely.
"""
def launch(book_id, chapter_id, user_id, model_choice):
    return None
