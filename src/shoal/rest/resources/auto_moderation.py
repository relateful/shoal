"""Endpoints for Auto Moderation rules. All need Manage Guild.

Discord: https://docs.discord.com/developers/resources/auto-moderation
"""

import builtins

from shoal.payloads.auto_moderation import (
    AutoModerationRule,
    CreateAutoModerationRuleParams,
    EditAutoModerationRuleParams,
)
from shoal.rest.endpoints import (
    CREATE_AUTO_MODERATION_RULE,
    DELETE_AUTO_MODERATION_RULE,
    GET_AUTO_MODERATION_RULE,
    LIST_AUTO_MODERATION_RULES_FOR_GUILD,
    MODIFY_AUTO_MODERATION_RULE,
)
from shoal.rest.requester import Resource


class AutoMod(Resource):
    """Auto Moderation rules.

    Use it as `rest.automod`, where `rest` is a `RestClient`.
    """

    __slots__ = ()

    async def list(self, guild_id: int) -> builtins.list[AutoModerationRule]:
        """List a guild's rules.

        Discord: https://docs.discord.com/developers/resources/auto-moderation#list-auto-moderation-rules-for-guild
        """
        return await self.request(
            LIST_AUTO_MODERATION_RULES_FOR_GUILD.compile(guild_id=guild_id), list[AutoModerationRule]
        )

    async def get(self, guild_id: int, rule_id: int) -> AutoModerationRule:
        """Get one rule.

        Discord: https://docs.discord.com/developers/resources/auto-moderation#get-auto-moderation-rule
        """
        return await self.request(
            GET_AUTO_MODERATION_RULE.compile(guild_id=guild_id, auto_moderation_rule_id=rule_id),
            AutoModerationRule,
        )

    async def create(
        self, guild_id: int, params: CreateAutoModerationRuleParams, *, reason: str | None = None
    ) -> AutoModerationRule:
        """Create a rule; a `TIMEOUT` action also needs Moderate Members.

        Discord: https://docs.discord.com/developers/resources/auto-moderation#create-auto-moderation-rule
        """
        return await self.request(
            CREATE_AUTO_MODERATION_RULE.compile(guild_id=guild_id),
            AutoModerationRule,
            body=params,
            reason=reason,
        )

    async def edit(
        self,
        guild_id: int,
        rule_id: int,
        params: EditAutoModerationRuleParams,
        *,
        reason: str | None = None,
    ) -> AutoModerationRule:
        """Change a rule.

        Discord: https://docs.discord.com/developers/resources/auto-moderation#modify-auto-moderation-rule
        """
        return await self.request(
            MODIFY_AUTO_MODERATION_RULE.compile(guild_id=guild_id, auto_moderation_rule_id=rule_id),
            AutoModerationRule,
            body=params,
            reason=reason,
        )

    async def delete(self, guild_id: int, rule_id: int, *, reason: str | None = None) -> None:
        """Delete a rule.

        Discord: https://docs.discord.com/developers/resources/auto-moderation#delete-auto-moderation-rule
        """
        await self.request_empty(
            DELETE_AUTO_MODERATION_RULE.compile(guild_id=guild_id, auto_moderation_rule_id=rule_id),
            reason=reason,
        )
