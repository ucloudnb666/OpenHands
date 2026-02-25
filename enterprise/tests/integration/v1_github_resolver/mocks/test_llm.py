"""TestLLM - A mock LLM for testing V1 GitHub Resolver.

This is a simplified version of the TestLLM from openhands.sdk.testing
that returns scripted responses without making real LLM API calls.
"""

from collections import deque
from typing import Any, ClassVar, Sequence

from litellm.types.utils import Choices, ModelResponse
from litellm.types.utils import Message as LiteLLMMessage
from pydantic import ConfigDict, Field, PrivateAttr

from openhands.sdk.llm.llm import LLM
from openhands.sdk.llm.llm_response import LLMResponse
from openhands.sdk.llm.message import Message, TextContent
from openhands.sdk.llm.streaming import TokenCallbackType
from openhands.sdk.llm.utils.metrics import MetricsSnapshot, TokenUsage
from openhands.sdk.tool.tool import ToolDefinition

__all__ = ['TestLLM', 'TestLLMExhaustedError']


class TestLLMExhaustedError(Exception):
    """Raised when TestLLM has no more scripted responses."""

    pass


class TestLLM(LLM):
    """A mock LLM for testing that returns scripted responses.

    TestLLM is a real LLM subclass that can be used anywhere an LLM is accepted.
    It returns pre-scripted responses without making any API calls.
    """

    # Prevent pytest from collecting this class as a test
    __test__ = False

    model: str = Field(default='test-model')
    _scripted_responses: deque[Message | Exception] = PrivateAttr(default_factory=deque)
    _call_count: int = PrivateAttr(default=0)

    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra='ignore', arbitrary_types_allowed=True
    )

    def __init__(self, **data: Any) -> None:
        # Extract scripted_responses before calling super().__init__
        scripted_responses = data.pop('scripted_responses', [])
        super().__init__(**data)
        self._scripted_responses = deque(list(scripted_responses))
        self._call_count = 0

    @classmethod
    def from_messages(
        cls,
        messages: list[Message | Exception],
        *,
        model: str = 'test-model',
        usage_id: str = 'test-llm',
        **kwargs: Any,
    ) -> 'TestLLM':
        """Create a TestLLM with scripted responses.

        Args:
            messages: List of Message or Exception objects to return in order.
            model: Model name (default: "test-model")
            usage_id: Usage ID for metrics (default: "test-llm")
            **kwargs: Additional LLM configuration options

        Returns:
            A TestLLM instance configured with the scripted responses.
        """
        return cls(
            model=model,
            usage_id=usage_id,
            scripted_responses=messages,
            **kwargs,
        )

    def completion(
        self,
        messages: list[Message],
        tools: Sequence[ToolDefinition] | None = None,
        _return_metrics: bool = False,
        add_security_risk_prediction: bool = False,
        on_token: TokenCallbackType | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Return the next scripted response.

        Args:
            messages: Input messages (ignored)
            tools: Available tools (ignored)
            _return_metrics: Whether to return metrics (ignored)
            add_security_risk_prediction: Add security risk field (ignored)
            on_token: Streaming callback (ignored)
            **kwargs: Additional arguments (ignored)

        Returns:
            LLMResponse containing the next scripted message.

        Raises:
            TestLLMExhaustedError: When no more scripted responses are available.
        """
        if not self._scripted_responses:
            raise TestLLMExhaustedError(
                f'TestLLM: no more scripted responses '
                f'(exhausted after {self._call_count} calls)'
            )

        item = self._scripted_responses.popleft()
        self._call_count += 1

        # Raise scripted exceptions
        if isinstance(item, Exception):
            raise item

        message = item

        # Create a minimal ModelResponse for raw_response
        raw_response = self._create_model_response(message)

        return LLMResponse(
            message=message,
            metrics=self._zero_metrics(),
            raw_response=raw_response,
        )

    def responses(
        self,
        messages: list[Message],
        tools: Sequence[ToolDefinition] | None = None,
        include: list[str] | None = None,
        store: bool | None = None,
        _return_metrics: bool = False,
        add_security_risk_prediction: bool = False,
        on_token: TokenCallbackType | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Return the next scripted response (delegates to completion)."""
        return self.completion(
            messages=messages,
            tools=tools,
            _return_metrics=_return_metrics,
            add_security_risk_prediction=add_security_risk_prediction,
            on_token=on_token,
            **kwargs,
        )

    def uses_responses_api(self) -> bool:
        """TestLLM always uses the completion path."""
        return False

    def _zero_metrics(self) -> MetricsSnapshot:
        """Return a zero-cost metrics snapshot."""
        return MetricsSnapshot(
            model_name=self.model,
            accumulated_cost=0.0,
            max_budget_per_task=None,
            accumulated_token_usage=TokenUsage(
                model=self.model,
                prompt_tokens=0,
                completion_tokens=0,
            ),
        )

    def _create_model_response(self, message: Message) -> ModelResponse:
        """Create a minimal ModelResponse from a Message."""
        # Build the LiteLLM message dict
        litellm_message_dict: dict[str, Any] = {
            'role': message.role,
            'content': self._content_to_string(message),
        }

        # Add tool_calls if present
        if message.tool_calls:
            litellm_message_dict['tool_calls'] = [
                {
                    'id': tc.id,
                    'type': 'function',
                    'function': {
                        'name': tc.name,
                        'arguments': tc.arguments,
                    },
                }
                for tc in message.tool_calls
            ]

        litellm_message = LiteLLMMessage(**litellm_message_dict)

        return ModelResponse(
            id=f'test-response-{self._call_count}',
            choices=[Choices(message=litellm_message, index=0, finish_reason='stop')],
            created=0,
            model=self.model,
            object='chat.completion',
        )

    def _content_to_string(self, message: Message) -> str:
        """Convert message content to a string."""
        parts = []
        for item in message.content:
            if isinstance(item, TextContent):
                parts.append(item.text)
        return '\n'.join(parts)

    @property
    def remaining_responses(self) -> int:
        """Return the number of remaining scripted responses."""
        return len(self._scripted_responses)

    @property
    def call_count(self) -> int:
        """Return the number of calls made to this TestLLM."""
        return self._call_count
