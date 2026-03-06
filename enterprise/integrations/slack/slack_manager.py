from typing import Any

import jwt
from integrations.manager import Manager
from integrations.models import Message, SourceType
from integrations.slack.slack_types import (
    SlackMessageView,
    SlackViewInterface,
    StartingConvoException,
)
from integrations.slack.slack_view import (
    SlackFactory,
    SlackNewConversationFromRepoFormView,
    SlackNewConversationView,
    SlackUnkownUserView,
    SlackUpdateExistingConversationView,
)
from integrations.utils import (
    HOST_URL,
    OPENHANDS_RESOLVER_TEMPLATES_DIR,
    get_session_expired_message,
    infer_repo_from_message,
)
from integrations.v1_utils import get_saas_user_auth
from jinja2 import Environment, FileSystemLoader
from server.constants import SLACK_CLIENT_ID
from server.utils.conversation_callback_utils import register_callback_processor
from slack_sdk.oauth import AuthorizeUrlGenerator
from slack_sdk.web.async_client import AsyncWebClient
from sqlalchemy import select
from storage.database import a_session_maker
from storage.slack_user import SlackUser

from openhands.core.logger import openhands_logger as logger
from openhands.integrations.provider import ProviderHandler
from openhands.integrations.service_types import ProviderTimeoutError, Repository
from openhands.server.shared import config, server_config
from openhands.server.types import (
    LLMAuthenticationError,
    MissingSettingsError,
    SessionExpiredError,
)
from openhands.server.user_auth.user_auth import UserAuth

authorize_url_generator = AuthorizeUrlGenerator(
    client_id=SLACK_CLIENT_ID,
    scopes=['app_mentions:read', 'chat:write'],
    user_scopes=['search:read'],
)


class SlackManager(Manager[SlackViewInterface]):
    def __init__(self, token_manager):
        self.token_manager = token_manager
        self.login_link = (
            'User has not yet authenticated: [Click here to Login to OpenHands]({}).'
        )

        self.jinja_env = Environment(
            loader=FileSystemLoader(OPENHANDS_RESOLVER_TEMPLATES_DIR + 'slack')
        )

    def _confirm_incoming_source_type(self, message: Message):
        if message.source != SourceType.SLACK:
            raise ValueError(f'Unexpected message source {message.source}')

    async def authenticate_user(
        self, slack_user_id: str
    ) -> tuple[SlackUser | None, UserAuth | None]:
        # We get the user and correlate them back to a user in OpenHands - if we can
        slack_user = None
        async with a_session_maker() as session:
            result = await session.execute(
                select(SlackUser).where(SlackUser.slack_user_id == slack_user_id)
            )
            slack_user = result.scalar_one_or_none()

            # slack_view.slack_to_openhands_user = slack_user # attach user auth info to view

        saas_user_auth = None
        if slack_user:
            saas_user_auth = await get_saas_user_auth(
                slack_user.keycloak_user_id, self.token_manager
            )
            # slack_view.saas_user_auth = await self._get_user_auth(slack_view.slack_to_openhands_user.keycloak_user_id)

        return slack_user, saas_user_auth

    async def _verify_repository(
        self, user_auth: UserAuth, repo_name: str
    ) -> Repository | None:
        """Verify if a repository exists and user has access to it.

        Args:
            user_auth: User authentication object
            repo_name: Full repository name (e.g., "owner/repo")

        Returns:
            Repository object if found, None otherwise

        Raises:
            ProviderTimeoutError: If the verification request times out
        """
        provider_tokens = await user_auth.get_provider_tokens()
        if provider_tokens is None:
            return None
        access_token = await user_auth.get_access_token()
        user_id = await user_auth.get_user_id()
        client = ProviderHandler(
            provider_tokens=provider_tokens,
            external_auth_token=access_token,
            external_auth_id=user_id,
        )
        try:
            return await client.verify_repo_provider(repo_name)
        except ProviderTimeoutError:
            # Re-raise timeout errors so caller can handle them
            raise
        except Exception:
            return None

    async def _get_repositories(self, user_auth: UserAuth) -> list[Repository]:
        provider_tokens = await user_auth.get_provider_tokens()
        if provider_tokens is None:
            return []
        access_token = await user_auth.get_access_token()
        user_id = await user_auth.get_user_id()
        client = ProviderHandler(
            provider_tokens=provider_tokens,
            external_auth_token=access_token,
            external_auth_id=user_id,
        )
        repos: list[Repository] = await client.get_repositories(
            'pushed', server_config.app_mode, None, None, None, None
        )
        return repos

    def _generate_repo_selection_form(
        self, repo_list: list[Repository], message_ts: str, thread_ts: str | None
    ):
        options = [
            {
                'text': {'type': 'plain_text', 'text': 'No Repository'},
                'value': '-',
            }
        ]
        options.extend(
            {
                'text': {
                    'type': 'plain_text',
                    'text': repo.full_name,
                },
                'value': repo.full_name,
            }
            for repo in repo_list
        )

        return [
            {
                'type': 'header',
                'text': {
                    'type': 'plain_text',
                    'text': 'Choose a repository',
                    'emoji': True,
                },
            },
            {
                'type': 'actions',
                'elements': [
                    {
                        'type': 'static_select',
                        'action_id': f'repository_select:{message_ts}:{thread_ts}',
                        'options': options,
                    }
                ],
            },
        ]

    async def receive_message(self, message: Message):
        self._confirm_incoming_source_type(message)

        slack_user, saas_user_auth = await self.authenticate_user(
            slack_user_id=message.message['slack_user_id']
        )

        try:
            slack_view = await SlackFactory.create_slack_view_from_payload(
                message, slack_user, saas_user_auth
            )
        except Exception as e:
            logger.error(
                f'[Slack]: Failed to create slack view: {e}',
                exc_info=True,
                stack_info=True,
            )
            return

        if isinstance(slack_view, SlackUnkownUserView):
            jwt_secret = config.jwt_secret
            if not jwt_secret:
                raise ValueError('Must configure jwt_secret')
            state = jwt.encode(
                message.message, jwt_secret.get_secret_value(), algorithm='HS256'
            )
            link = authorize_url_generator.generate(state)
            msg = self.login_link.format(link)

            logger.info('slack_not_yet_authenticated')
            await self.send_message(msg, slack_view, ephemeral=True)
            return

        if not await self.is_job_requested(message, slack_view):
            return

        await self.start_job(slack_view)

    async def send_message(
        self,
        message: str | dict[str, Any],
        slack_view: SlackMessageView,
        ephemeral: bool = False,
    ):
        """Send a message to Slack.

        Args:
            message: The message content. Can be a string (for simple text) or
                     a dict with 'text' and 'blocks' keys (for structured messages).
            slack_view: The Slack view object containing channel/thread info.
                        Can be either SlackMessageView (for unauthenticated users)
                        or SlackViewInterface (for authenticated users).
            ephemeral: If True, send as an ephemeral message visible only to the user.
        """
        client = AsyncWebClient(token=slack_view.bot_access_token)
        if ephemeral and isinstance(message, str):
            await client.chat_postEphemeral(
                channel=slack_view.channel_id,
                markdown_text=message,
                user=slack_view.slack_user_id,
                thread_ts=slack_view.thread_ts,
            )
        elif ephemeral and isinstance(message, dict):
            await client.chat_postEphemeral(
                channel=slack_view.channel_id,
                user=slack_view.slack_user_id,
                thread_ts=slack_view.thread_ts,
                text=message['text'],
                blocks=message['blocks'],
            )
        else:
            await client.chat_postMessage(
                channel=slack_view.channel_id,
                markdown_text=message,
                thread_ts=slack_view.message_ts,
            )

    async def is_job_requested(
        self, message: Message, slack_view: SlackViewInterface
    ) -> bool:
        """A job is always request we only receive webhooks for events associated with the slack bot
        This method really just checks
            1. Is the user is authenticated
            2. Do we have the necessary information to start a job (either by inferring the selected repo, otherwise asking the user)
        """
        # Infer repo from user message is not needed; user selected repo from the form or is updating existing convo
        if isinstance(slack_view, SlackUpdateExistingConversationView):
            return True
        elif isinstance(slack_view, SlackNewConversationFromRepoFormView):
            return True
        elif isinstance(slack_view, SlackNewConversationView):
            user = slack_view.slack_to_openhands_user

            # First, try to infer repos from the user's message
            inferred_repos = infer_repo_from_message(slack_view.user_msg)

            # Check if multiple repos were mentioned in the message
            if len(inferred_repos) >= 2:
                repo_list_str = '\n• '.join(inferred_repos[:10])
                if len(inferred_repos) > 10:
                    repo_list_str += f'\n• ... and {len(inferred_repos) - 10} more'

                clarify_msg = (
                    f'I found multiple repositories mentioned in your message:\n'
                    f'• {repo_list_str}\n\n'
                    'Please specify only one repository name so I can determine '
                    'which one you want to use.'
                )
                logger.info(
                    'multiple_repos_in_message',
                    extra={
                        'slack_user_id': user.slack_user_id,
                        'inferred_repos': inferred_repos,
                        'count': len(inferred_repos),
                    },
                )
                await self.send_message(clarify_msg, slack_view, ephemeral=True)
                return False

            if len(inferred_repos) == 1:
                inferred_repo = inferred_repos[0]
                # User specified a repo - verify it exists directly
                logger.info(
                    f'[Slack] User specified repo "{inferred_repo}", verifying',
                    extra={
                        'slack_user_id': user.slack_user_id,
                        'keycloak_user_id': user.keycloak_user_id,
                        'inferred_repo': inferred_repo,
                    },
                )

                try:
                    repository = await self._verify_repository(
                        slack_view.saas_user_auth, inferred_repo
                    )
                except ProviderTimeoutError:
                    logger.warning(
                        'repo_verify_timeout',
                        extra={
                            'slack_user_id': user.slack_user_id,
                            'keycloak_user_id': user.keycloak_user_id,
                            'inferred_repo': inferred_repo,
                        },
                    )
                    timeout_msg = (
                        f'The verification of repository "{inferred_repo}" timed out. '
                        'Please try again.'
                    )
                    await self.send_message(timeout_msg, slack_view, ephemeral=True)
                    return False

                if repository:
                    # Repository found - proceed with job
                    slack_view.selected_repo = repository.full_name
                    logger.info(
                        f'[Slack] Verified repository: {repository.full_name}'
                    )
                    return True

                # Repository not found - fall through to fetch all repos and show dropdown
                logger.info(
                    'repo_not_found_falling_back',
                    extra={
                        'slack_user_id': user.slack_user_id,
                        'inferred_repo': inferred_repo,
                    },
                )

            # No repo inferred from message, or no matches found - fetch all repos and show selection form
            logger.info(
                f'[Slack] No repo specified, fetching repository list for user {user.slack_display_name}'
            )
            try:
                user_repos: list[Repository] = await self._get_repositories(
                    slack_view.saas_user_auth
                )
            except ProviderTimeoutError:
                logger.warning(
                    'repo_query_timeout',
                    extra={
                        'slack_user_id': user.slack_user_id,
                        'keycloak_user_id': user.keycloak_user_id,
                    },
                )
                timeout_msg = (
                    'The repository selection timed out while fetching your repository list. '
                    'Please re-send your message with a specific repository name '
                    '(e.g., "owner/repo-name") to help me find it faster.'
                )
                await self.send_message(timeout_msg, slack_view, ephemeral=True)
                return False

            logger.info(
                'render_repository_selector',
                extra={
                    'slack_user_id': user.slack_user_id,
                    'keycloak_user_id': user.keycloak_user_id,
                    'message_ts': slack_view.message_ts,
                    'thread_ts': slack_view.thread_ts,
                },
            )

            repo_selection_msg = {
                'text': 'Choose a Repository:',
                'blocks': self._generate_repo_selection_form(
                    user_repos[:99], slack_view.message_ts, slack_view.thread_ts
                ),
            }
            await self.send_message(repo_selection_msg, slack_view, ephemeral=True)

            return False

        return True

    async def start_job(self, slack_view: SlackViewInterface) -> None:
        # Importing here prevents circular import
        from server.conversation_callback_processor.slack_callback_processor import (
            SlackCallbackProcessor,
        )

        try:
            msg_info = None
            user_info = slack_view.slack_to_openhands_user
            try:
                logger.info(
                    f'[Slack] Starting job for user {user_info.slack_display_name} (id={user_info.slack_user_id})',
                    extra={'keyloak_user_id': user_info.keycloak_user_id},
                )
                conversation_id = await slack_view.create_or_update_conversation(
                    self.jinja_env
                )

                logger.info(
                    f'[Slack] Created conversation {conversation_id} for user {user_info.slack_display_name}'
                )

                # Only add SlackCallbackProcessor for new conversations (not updates) and non-v1 conversations
                if (
                    not isinstance(slack_view, SlackUpdateExistingConversationView)
                    and not slack_view.v1_enabled
                ):
                    # We don't re-subscribe for follow up messages from slack.
                    # Summaries are generated for every messages anyways, we only need to do
                    # this subscription once for the event which kicked off the job.

                    processor = SlackCallbackProcessor(
                        slack_user_id=slack_view.slack_user_id,
                        channel_id=slack_view.channel_id,
                        message_ts=slack_view.message_ts,
                        thread_ts=slack_view.thread_ts,
                        team_id=slack_view.team_id,
                    )

                    # Register the callback processor
                    register_callback_processor(conversation_id, processor)

                    logger.info(
                        f'[Slack] Created callback processor for conversation {conversation_id}'
                    )
                elif isinstance(slack_view, SlackUpdateExistingConversationView):
                    logger.info(
                        f'[Slack] Skipping callback processor for existing conversation update {conversation_id}'
                    )
                elif slack_view.v1_enabled:
                    logger.info(
                        f'[Slack] Skipping callback processor for v1 conversation {conversation_id}'
                    )

                msg_info = slack_view.get_response_msg()

            except MissingSettingsError as e:
                logger.warning(
                    f'[Slack] Missing settings error for user {user_info.slack_display_name}: {str(e)}'
                )

                msg_info = f'{user_info.slack_display_name} please re-login into [OpenHands Cloud]({HOST_URL}) before starting a job.'

            except LLMAuthenticationError as e:
                logger.warning(
                    f'[Slack] LLM authentication error for user {user_info.slack_display_name}: {str(e)}'
                )

                msg_info = f'@{user_info.slack_display_name} please set a valid LLM API key in [OpenHands Cloud]({HOST_URL}) before starting a job.'

            except SessionExpiredError as e:
                logger.warning(
                    f'[Slack] Session expired for user {user_info.slack_display_name}: {str(e)}'
                )

                msg_info = get_session_expired_message(user_info.slack_display_name)

            except StartingConvoException as e:
                msg_info = str(e)

            await self.send_message(msg_info, slack_view)

        except Exception:
            logger.exception('[Slack]: Error starting job')
            await self.send_message(
                'Uh oh! There was an unexpected error starting the job :(', slack_view
            )
