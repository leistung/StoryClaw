import unittest
from unittest.mock import patch
from storyclaw.llm import build_chat_client

class ModelAdapter(unittest.TestCase):
    def test_provider_extra_body_forwarded(self):
        with patch('langchain_openai.ChatOpenAI') as client:
            build_chat_client(format='openai_chat', model='glm-5.1', api_key='test',
                base_url='https://open.bigmodel.cn/api/paas/v4',extra_body={'thinking':{'type':'disabled'}})
        self.assertEqual(client.call_args.kwargs['extra_body'], {'thinking':{'type':'disabled'}})

    def test_other_providers_do_not_receive_thinking(self):
        with patch('langchain_openai.ChatOpenAI') as client:
            build_chat_client(format='openai_chat', model='test', api_key='test')
        self.assertNotIn('extra_body', client.call_args.kwargs)
