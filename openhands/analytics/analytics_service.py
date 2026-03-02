"""Core analytics service for OpenHands.

Provides a thin wrapper around the PostHog SDK with:
- Consent gate: all calls are no-ops when consented=False
- OSS/SaaS dual-mode: $process_person_profile is set to False in OSS mode;
  set_person_properties and group_identify are SaaS-only
- Common properties: app_mode, is_feature_env added to every event
- Feature-env distinct_id prefix: FEATURE_ prefix for staging/feature envs
- SDK error isolation: all exceptions are caught and logged, never raised

This module must NOT import from enterprise/. It receives all configuration
via constructor args.
"""

from typing import Any

from posthog import Posthog

from openhands.core.logger import openhands_logger as logger
from openhands.server.types import AppMode


class AnalyticsService:
    """Server-side analytics service backed by PostHog.

    Args:
        api_key: PostHog project API key. Pass an empty string to disable.
        host: PostHog ingest host URL.
        app_mode: AppMode.OPENHANDS (OSS) or AppMode.SAAS.
        is_feature_env: True when running in a feature/staging environment.
    """

    def __init__(
        self,
        api_key: str,
        host: str,
        app_mode: AppMode,
        is_feature_env: bool,
    ) -> None:
        self._app_mode = app_mode
        self._is_feature_env = is_feature_env
        self._client: Posthog = Posthog(
            project_api_key=api_key,
            host=host,
            disabled=not api_key,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def capture(
        self,
        distinct_id: str,
        event: str,
        properties: dict[str, Any] | None = None,
        org_id: str | None = None,
        session_id: str | None = None,
        consented: bool = True,
    ) -> None:
        """Capture a server-side event.

        Consent gate: returns immediately when consented=False.
        Common properties (app_mode, is_feature_env, and optionally org_id /
        $session_id / $process_person_profile) are merged with caller-provided
        properties before forwarding to PostHog.
        """
        if not consented:
            return

        merged = self._common_properties(org_id=org_id, session_id=session_id)
        if properties:
            merged.update(properties)

        try:
            self._client.capture(
                distinct_id=self._distinct_id(distinct_id),
                event=event,
                properties=merged,
            )
        except Exception:
            logger.exception('AnalyticsService.capture failed')

    def set_person_properties(
        self,
        distinct_id: str,
        properties: dict[str, Any],
        consented: bool = True,
    ) -> None:
        """Set person properties in PostHog (SaaS-only).

        No-op in OSS mode or when consented=False.
        """
        if not consented:
            return
        if self._app_mode != AppMode.SAAS:
            return

        try:
            self._client.set(
                distinct_id=self._distinct_id(distinct_id),
                properties=properties,
            )
        except Exception:
            logger.exception('AnalyticsService.set_person_properties failed')

    def group_identify(
        self,
        group_type: str,
        group_key: str,
        properties: dict[str, Any],
        distinct_id: str | None = None,
        consented: bool = True,
    ) -> None:
        """Associate a group with properties (SaaS-only).

        No-op in OSS mode or when consented=False.
        """
        if not consented:
            return
        if self._app_mode != AppMode.SAAS:
            return

        try:
            kwargs: dict[str, Any] = {
                'group_type': group_type,
                'group_key': group_key,
                'properties': properties,
            }
            if distinct_id is not None:
                kwargs['distinct_id'] = self._distinct_id(distinct_id)
            self._client.group_identify(**kwargs)
        except Exception:
            logger.exception('AnalyticsService.group_identify failed')

    def shutdown(self) -> None:
        """Flush and shut down the PostHog client.

        Safe to call multiple times. SDK errors are logged, not raised.
        """
        try:
            self._client.shutdown()
        except Exception:
            logger.exception('AnalyticsService.shutdown failed')

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _distinct_id(self, user_id: str) -> str:
        """Return the PostHog distinct_id for the given user.

        In feature/staging environments, prefixes with 'FEATURE_' to keep
        test traffic separate from production profiles.
        """
        if self._is_feature_env:
            return f'FEATURE_{user_id}'
        return user_id

    def _common_properties(
        self,
        org_id: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Build the base property dict included on every event."""
        props: dict[str, Any] = {
            'app_mode': self._app_mode.value,
            'is_feature_env': self._is_feature_env,
        }

        if org_id is not None:
            props['org_id'] = org_id

        if session_id is not None:
            props['$session_id'] = session_id

        # PostHog person profiles are not useful in OSS mode (no user accounts)
        if self._app_mode != AppMode.SAAS:
            props['$process_person_profile'] = False

        return props
