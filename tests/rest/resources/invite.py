import pytest

from shoal.core.codec import PayloadDecodeError
from shoal.core.snowflake import Snowflake
from shoal.payloads import GetInviteParams
from shoal.rest.resources.invite import parse_target_users
from tests.support.json_payloads import INVITE
from tests.support.multipart import FormPart
from tests.support.rest import EndpointCase, check_endpoint, endpoint_cases

INVITES = "/invites/0vCdhLbwjZZTWZLD"
JOB_STATUS: dict[str, object] = {
    "status": 3,
    "total_users": 100,
    "processed_users": 41,
    "created_at": "2025-01-08T12:00:00+00:00",
    "completed_at": None,
    "error_message": "Failed to parse CSV file",
}
"""Discord's example."""

CASES = [
    EndpointCase(
        name="get invite",
        call=lambda client: client.get_invite(
            "0vCdhLbwjZZTWZLD", GetInviteParams(with_counts=True, guild_scheduled_event_id=Snowflake(4))
        ),
        method="GET",
        path=f"{INVITES}?with_counts=true&guild_scheduled_event_id=4",
        response={**INVITE, "approximate_presence_count": 5, "approximate_member_count": 10},
    ),
    EndpointCase(
        name="delete invite",
        call=lambda client: client.delete_invite("0vCdhLbwjZZTWZLD", reason="leaked"),
        method="DELETE",
        path=INVITES,
        response=INVITE,
        reason="leaked",
    ),
    EndpointCase(
        name="get target users",
        call=lambda client: client.get_target_users("0vCdhLbwjZZTWZLD"),
        method="GET",
        path=f"{INVITES}/target-users",
        response=b"user_id\r\n1\r\n2\r\n",
        result=["1", "2"],
    ),
    EndpointCase(
        name="add target user",
        call=lambda client: client.add_target_user("0vCdhLbwjZZTWZLD", 1),
        method="PUT",
        path=f"{INVITES}/target-users/1",
    ),
    EndpointCase(
        name="remove target user",
        call=lambda client: client.remove_target_user("0vCdhLbwjZZTWZLD", 1),
        method="DELETE",
        path=f"{INVITES}/target-users/1",
    ),
    EndpointCase(
        name="replace target users",
        call=lambda client: client.update_target_users("0vCdhLbwjZZTWZLD", [1, 2]),
        method="PUT",
        path=f"{INVITES}/target-users",
        files=(FormPart("target_users_file", "target_users.csv", "text/csv", b"1\n2\n"),),
    ),
    EndpointCase(
        name="bulk add target users",
        call=lambda client: client.bulk_add_target_users("0vCdhLbwjZZTWZLD", [1, 2]),
        method="POST",
        path=f"{INVITES}/target-users/bulk-add",
        body={"user_ids": ["1", "2"]},
    ),
    EndpointCase(
        name="bulk delete target users",
        call=lambda client: client.bulk_delete_target_users("0vCdhLbwjZZTWZLD", [1]),
        method="POST",
        path=f"{INVITES}/target-users/bulk-delete",
        body={"user_ids": ["1"]},
    ),
    EndpointCase(
        name="job status",
        call=lambda client: client.get_target_users_job_status("0vCdhLbwjZZTWZLD"),
        method="GET",
        path=f"{INVITES}/target-users/job-status",
        response=JOB_STATUS,
    ),
]


@endpoint_cases(CASES)
async def test_invite_endpoints(case: EndpointCase) -> None:
    await check_endpoint(case)


@pytest.mark.parametrize(
    ("body", "ids"),
    [
        (b"user_id\r\n1\r\n2\r\n", [1, 2]),
        (b'\xef\xbb\xbfuser_id\n"3"\n4,\n', [3, 4]),
        (b"", []),
        (b"user_id\n", []),
    ],
    ids=["documented", "bom quotes and commas", "empty", "header only"],
)
def test_target_user_csv_is_read(body: bytes, ids: list[int]) -> None:
    assert parse_target_users(body) == ids


@pytest.mark.parametrize(
    "body", [b"user_id\nnobody\n", b"\xff", b"\xc2\xb2"], ids=["word", "not utf-8", "superscript"]
)
def test_a_target_user_csv_that_cannot_be_read_is_an_error(body: bytes) -> None:
    with pytest.raises(PayloadDecodeError):
        parse_target_users(body)
