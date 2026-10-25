"""Quota-only model failover; never combine partial streams from different models."""
from __future__ import annotations
import logging
from .errors import model_failure
from .metering import wrap_model

log = logging.getLogger(__name__)

class QuotaFallbackModel:
    """Branches are lazy (factory, billing model id) pairs, each metered separately."""
    handles_metering = True

    def __init__(self, branches, bindings=()):
        self.branches = tuple(branches)
        self.bindings = tuple(bindings)
        self.max_tokens = 8192

    def bind(self, **kwargs):
        return type(self)(self.branches, self.bindings + (("bind", (), kwargs),))

    def bind_tools(self, tools, **kwargs):
        return type(self)(self.branches, self.bindings + (("bind_tools", (tools,), kwargs),))

    def _client(self, factory, model_id):
        client = wrap_model(factory(), model_id)
        for method, args, kwargs in self.bindings:
            client = getattr(client, method)(*args, **kwargs)
        return client

    def _can_fallback(self, exc, index):
        return index + 1 < len(self.branches) and model_failure(exc)['error_code'] == 'supplier_quota'

    @staticmethod
    def _annotate(response, model_id):
        metadata = getattr(response, 'response_metadata', None)
        if isinstance(metadata, dict):
            metadata['storyclaw_model_id'] = model_id
        return response

    async def ainvoke(self, messages, **kwargs):
        for index, (factory, model_id) in enumerate(self.branches):
            try:
                return self._annotate(await self._client(factory, model_id).ainvoke(messages, **kwargs), model_id)
            except Exception as exc:
                if not self._can_fallback(exc, index):
                    raise
                log.warning('quota_fallback from=%s to=%s', model_id, self.branches[index + 1][1])

    async def astream(self, messages, **kwargs):
        for index, (factory, model_id) in enumerate(self.branches):
            emitted = False
            try:
                async for chunk in self._client(factory, model_id).astream(messages, **kwargs):
                    if not emitted:
                        self._annotate(chunk, model_id)
                    emitted = True
                    yield chunk
                return
            except Exception as exc:
                if emitted or not self._can_fallback(exc, index):
                    raise
                log.warning('quota_fallback from=%s to=%s', model_id, self.branches[index + 1][1])
