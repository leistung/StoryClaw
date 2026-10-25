"""Public application-service facade; implementation is split by responsibility."""
from .conversation import chat
from .conversation import chat_stream
from .chapters import generate_chapter
from .chapters import generate_chapter_stream
from .chapters import modify_chapter
from .history import list_sessions
from .history import list_messages
from .history import retry
from .history import feedback
from .context import _model_choice
from .context import _build_input
from .context import _find_next_chapter
from .context import _extract_book_id
from .context import _extract_chapter_id
