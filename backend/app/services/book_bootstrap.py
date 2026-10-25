"""Legacy automatic bootstrap retired in favor of tracked, author-confirmed jobs."""
def launch(book_id,user_id,flags):
    if any(flags.values()):
        raise ValueError('请在工作台逐步发起创作任务，不再自动初始化 AI 内容')
