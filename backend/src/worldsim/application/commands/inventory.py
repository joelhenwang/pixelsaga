"""Inventory commands (owned by S2-PROGRESS-001).

Instances carry their single holder: giving sets it, transfer moves
it version-guarded, and ground items (no holder) wait where left.
Every change lands beside its audit command in one transaction.
"""

from __future__ import annotations

from uuid import uuid4

from worldsim.application.transactions.canonical import canonical_input_hash
from worldsim.application.unit_of_work import UnitOfWork
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.ids import (
    CharacterId,
    ItemInstanceId,
    WorldId,
    new_item_instance_id,
)
from worldsim.domain.items import ItemDefinition
from worldsim.domain.progress import ItemInstance


async def give_item(
    uow: UnitOfWork,
    actor_role: str,
    world_id: WorldId,
    item_key: str,
    owner_id: CharacterId | None,
    catalog: dict[str, ItemDefinition],
    quantity: int = 1,
) -> ItemInstance:
    """Create one instance for a holder (or the ground)."""
    if item_key not in catalog:
        raise DomainError(ErrorCode.NOT_FOUND, f"unknown item: {item_key}")
    if quantity < 1:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "quantity needs counting")
    if owner_id is not None:
        owner = await uow.characters.get(owner_id)
        if owner.world_id != world_id:
            raise DomainError(ErrorCode.NOT_FOUND, "holder is not in this world")
    key = f"item-give:{world_id.hex}:{item_key}:{owner_id.hex if owner_id else 'ground'}:{uuid4().hex}"
    payload: dict[str, object] = {
        "item_key": item_key,
        "owner_id": str(owner_id) if owner_id else None,
        "quantity": quantity,
    }
    await uow.commands.add(
        command_id=uuid4(),
        world_id=world_id,
        key=key,
        actor_role=actor_role,
        command_type="give_item",
        expected_versions={},
        payload=payload,
        input_hash=canonical_input_hash({"key": key, "payload": payload}),
    )
    item = ItemInstance(
        id=new_item_instance_id(),
        world_id=world_id,
        item_key=item_key,
        owner_id=owner_id,
        quantity=quantity,
    )
    await uow.inventory.add_item(item)
    await uow.commit()
    return item


async def transfer_item(
    uow: UnitOfWork,
    actor_role: str,
    item_id: ItemInstanceId,
    to_owner_id: CharacterId | None,
) -> ItemInstance:
    """Move one instance to a new holder (or drop it)."""
    item = await uow.inventory.get_item(item_id)
    if to_owner_id is not None:
        owner = await uow.characters.get(to_owner_id)
        if owner.world_id != item.world_id:
            raise DomainError(ErrorCode.NOT_FOUND, "holder is not in this world")
    if item.owner_id == to_owner_id:
        return item
    target = to_owner_id.hex if to_owner_id else "ground"
    key = f"item-transfer:{item.id.hex}:{target}:{uuid4().hex}"
    payload: dict[str, object] = {
        "item_id": str(item.id),
        "to_owner_id": str(to_owner_id) if to_owner_id else None,
    }
    await uow.commands.add(
        command_id=uuid4(),
        world_id=item.world_id,
        key=key,
        actor_role=actor_role,
        command_type="transfer_item",
        expected_versions={},
        payload=payload,
        input_hash=canonical_input_hash({"key": key, "payload": payload}),
    )
    saved = await uow.inventory.save_item(
        item.model_copy(update={"owner_id": to_owner_id}), item.version
    )
    await uow.commit()
    return saved
