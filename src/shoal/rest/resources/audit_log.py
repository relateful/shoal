"""Endpoints for audit logs.

Discord: https://docs.discord.com/developers/resources/audit-log
"""

from shoal.payloads.audit_log import AuditLog, GetAuditLogParams
from shoal.rest.endpoints import GET_GUILD_AUDIT_LOG
from shoal.rest.requester import Resource, query_of


class AuditLogs(Resource):
    """A guild's audit log.

    Use it as `rest.audit_logs`, where `rest` is a `RestClient`.
    """

    __slots__ = ()

    async def get(self, guild_id: int, params: GetAuditLogParams | None = None) -> AuditLog:
        """Get a page of a guild's audit log. Needs View Audit Log.

        Discord: https://docs.discord.com/developers/resources/audit-log#get-guild-audit-log
        """
        return await self.request(
            GET_GUILD_AUDIT_LOG.compile(guild_id=guild_id),
            AuditLog,
            query=query_of(params) if params is not None else None,
        )
