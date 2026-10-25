"""Public application-service facade; implementation is split by responsibility."""
from .editing import polish_chapter
from .editing import continue_writing
from .batch import multi_write
from .analysis import analyze_book
from .assistance import assist_brainstorm
from .assistance import assist_title_generation
from .assistance import assist_scene_enhance
from .assistance import assist_dialogue_polish
from .assistance import assist_reading_config_gen
from .scenes import plan_chapter_scenes
from .context import _model_choice
from .context import _save_assistant_msg
from .context import _load_outline
from .context import _load_book_meta
