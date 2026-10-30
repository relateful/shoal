import pytest

from shoal.core.snowflake import Snowflake
from shoal.models.overwrite import PermissionOverwrite
from shoal.payloads.channel import Overwrite, OverwriteType
from shoal.payloads.permissions import Permissions
from tests.support.calls import call_unchecked


def test_pair_splits_allowed_and_denied() -> None:
    overwrite = PermissionOverwrite(send_messages=True, view_channel=False, speak=None)
    assert overwrite.pair() == (Permissions(send_messages=True), Permissions(view_channel=True))
    assert overwrite.send_messages is True
    assert overwrite.view_channel is False
    assert overwrite.speak is None


def test_aliases_name_the_same_permission() -> None:
    overwrite = PermissionOverwrite(read_messages=False, manage_permissions=True)
    assert overwrite.view_channel is False
    assert overwrite.read_messages is False
    assert overwrite.pair() == (Permissions(manage_roles=True), Permissions(view_channel=True))


def test_attributes_set_and_clear() -> None:
    overwrite = PermissionOverwrite()
    assert overwrite.is_empty()
    overwrite.send_messages = True
    assert not overwrite.is_empty()
    overwrite.send_messages = None
    assert overwrite.is_empty()
    with pytest.raises(TypeError, match="True, False or None"):
        overwrite.send_messages = 1


def test_unknown_permissions_are_refused() -> None:
    with pytest.raises(AttributeError, match="'fly' is not a permission"):
        PermissionOverwrite(fly=True)
    with pytest.raises(AttributeError, match="is not a permission"):
        call_unchecked(getattr, PermissionOverwrite(), "fly")


def test_from_pair_round_trips_and_deny_wins() -> None:
    overwrite = PermissionOverwrite.from_pair(Permissions(speak=True, stream=True), Permissions(stream=True))
    assert overwrite == PermissionOverwrite(speak=True, stream=False)
    assert PermissionOverwrite.from_pair(*overwrite.pair()) == overwrite
    assert overwrite != object()


def test_from_overwrite_reads_a_channel_overwrite() -> None:
    raw = Overwrite(
        id=Snowflake(1), type=OverwriteType.ROLE, allow=Permissions(speak=True), deny=Permissions.none()
    )
    assert PermissionOverwrite.from_overwrite(raw) == PermissionOverwrite(speak=True)


def test_iterates_every_permission_in_bit_order() -> None:
    values = dict(PermissionOverwrite(kick_members=True))
    assert values["kick_members"] is True
    assert values["ban_members"] is None
    assert next(iter(PermissionOverwrite()))[0] == "create_instant_invite"
    assert len(values) == len(Permissions.known_flags)


def test_repr_and_unhashable() -> None:
    assert repr(PermissionOverwrite(speak=True)) == "PermissionOverwrite(speak=True)"
    with pytest.raises(TypeError):
        hash(PermissionOverwrite())
