"""Endpoints for audit logs.

Discord: https://docs.discord.com/developers/resources/audit-log
"""

from shoal.payloads.audit_log import AuditLog, GetGuildAuditLogParams
from shoal.rest.endpoints import GET_GUILD_AUDIT_LOG
from shoal.rest.requester import Requester, query_of


class AuditLogEndpoints(Requester):
    """Endpoints for audit logs; part of `RestClient`."""

    __slots__ = ()

    async def get_guild_audit_log(
        self, guild_id: int, params: GetGuildAuditLogParams | None = None
    ) -> AuditLog:
        """Get a page of a guild's audit log. Needs View Audit Log.

        Discord: https://docs.discord.com/developers/resources/audit-log#get-guild-audit-log
        """
        return await self.request(
            GET_GUILD_AUDIT_LOG.compile(guild_id=guild_id),
            AuditLog,
            query=query_of(params) if params is not None else None,
        )
