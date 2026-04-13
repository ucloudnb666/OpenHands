import logging
from typing import Any
from uuid import UUID

import httpx
from pydantic import Field

from openhands.app_server.event_callback.event_callback_models import (
    EventCallback,
    EventCallbackProcessor,
)
from openhands.app_server.event_callback.event_callback_result_models import (
    EventCallbackResult,
    EventCallbackResultStatus,
)
from openhands.sdk import Event
from openhands.sdk.event import ConversationStateUpdateEvent
from openhands.utils.http_session import httpx_verify_option

_logger = logging.getLogger(__name__)

JIRA_CLOUD_API_URL = 'https://api.atlassian.com/ex/jira'


class JiraV1CallbackProcessor(EventCallbackProcessor):
    """Callback processor for Jira V1 integrations."""

    jira_view_data: dict[str, Any] = Field(default_factory=dict)
    should_request_summary: bool = Field(default=True)

    async def __call__(
        self,
        conversation_id: UUID,
        callback: EventCallback,
        event: Event,
    ) -> EventCallbackResult | None:
        """Process events for Jira V1 integration."""
        # Only handle ConversationStateUpdateEvent for execution_status
        if not isinstance(event, ConversationStateUpdateEvent):
            return None

        if event.key != 'execution_status':
            return None

        _logger.info('[Jira V1] Callback agent state was %s', event)

        # Only request summary when execution has finished successfully
        if event.value != 'finished':
            return None

        _logger.info(
            '[Jira V1] Should request summary: %s', self.should_request_summary
        )

        if not self.should_request_summary:
            return None

        self.should_request_summary = False

        try:
            _logger.info(f'[Jira V1] Requesting summary {conversation_id}')
            summary = await self._request_summary(conversation_id)
            _logger.info(
                f'[Jira V1] Posting summary {conversation_id}',
                extra={'summary': summary},
            )
            await self._post_summary_to_jira(summary)

            return EventCallbackResult(
                status=EventCallbackResultStatus.SUCCESS,
                event_callback_id=callback.id,
            )
        except Exception as e:
            _logger.error(f'[Jira V1] Failed to post summary: {e}')
            return EventCallbackResult(
                status=EventCallbackResultStatus.ERROR,
                event_callback_id=callback.id,
                detail=str(e),
            )

    async def _request_summary(self, conversation_id: UUID) -> str:
        """Request the conversation summary."""
        from openhands.app_server.config import get_agent_server_url_from_conversation
        from openhands.app_server.event_callback.util import (
            get_agent_server_url_from_sandbox,
        )

        agent_server_url = await get_agent_server_url_from_conversation(
            str(conversation_id)
        )

        if not agent_server_url:
            agent_server_url = get_agent_server_url_from_sandbox()

        summary_url = f'{agent_server_url}/api/conversations/{conversation_id}/summary'

        async with httpx.AsyncClient(verify=httpx_verify_option()) as client:
            response = await client.get(summary_url)
            response.raise_for_status()
            data = response.json()
            return data.get('summary', '')

    async def _post_summary_to_jira(self, summary: str):
        """Post the summary back to the Jira issue."""
        jira_workspace = self.jira_view_data.get('jira_workspace')
        svc_acc_email = self.jira_view_data.get('svc_acc_email')
        decrypted_api_key = self.jira_view_data.get('decrypted_api_key')
        issue_key = self.jira_view_data.get('issue_key')

        if not all([jira_workspace, svc_acc_email, decrypted_api_key, issue_key]):
            _logger.warning('[Jira V1] Missing required data for posting summary')
            return

        # Add a comment to the Jira issue with the summary
        comment_url = f'{JIRA_CLOUD_API_URL}/{jira_workspace.jira_cloud_id}/rest/api/2/issue/{issue_key}/comment'

        comment_body = {
            'body': {
                'type': 'doc',
                'version': 1,
                'content': [
                    {
                        'type': 'paragraph',
                        'content': [
                            {
                                'type': 'text',
                                'text': f'OpenHands resolved this issue:\n\n{summary}',
                            }
                        ],
                    }
                ],
            }
        }

        async with httpx.AsyncClient(verify=httpx_verify_option()) as client:
            response = await client.post(
                comment_url,
                auth=(svc_acc_email, decrypted_api_key),
                json=comment_body,
            )
            response.raise_for_status()
            _logger.info(f'[Jira V1] Posted summary to {issue_key}')
