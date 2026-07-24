from collections.abc import AsyncGenerator, Sequence
from typing import Any

from agentscope.credential import CredentialBase
from agentscope.message import Msg
from agentscope.model import ChatModelBase, ChatResponse
from pydantic import BaseModel

ScriptedResult = ChatResponse | Sequence[ChatResponse] | Exception


class FakeCredential(CredentialBase):
    @classmethod
    def get_chat_model_class(cls) -> type["ScriptedChatModel"]:
        return ScriptedChatModel


class ScriptedChatModel(ChatModelBase):
    class Parameters(BaseModel):
        pass

    def __init__(self, results: Sequence[ScriptedResult], *, name: str = "fake") -> None:
        super().__init__(
            credential=FakeCredential(),
            model=name,
            parameters=self.Parameters(),
            stream=True,
            max_retries=0,
        )
        self._results = list(results)
        self.call_count = 0

    async def _call_api(
        self,
        model_name: str,
        messages: list[Msg],
        tools: list[dict] | None = None,
        tool_choice: Any = None,
        **kwargs: Any,
    ) -> ChatResponse | AsyncGenerator[ChatResponse, None]:
        del model_name, messages, tools, tool_choice, kwargs
        self.call_count += 1
        result = self._results.pop(0)
        if isinstance(result, Exception):
            raise result
        if isinstance(result, ChatResponse):
            return result

        async def stream() -> AsyncGenerator[ChatResponse, None]:
            for chunk in result:
                yield chunk

        return stream()
