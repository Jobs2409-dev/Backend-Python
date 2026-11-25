import json

from django.conf import settings
from redis.asyncio import Redis


PRESENCE_KEY_PREFIX = "reclamos:presence:categoria:"
DEFAULT_GROUP_EXPIRY = 86400


def _presence_key(categoria_id: str) -> str:
    return f"{PRESENCE_KEY_PREFIX}{categoria_id}"


def _redis_client() -> Redis:
    return Redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
    )


def _group_expiry() -> int:
    config = settings.CHANNEL_LAYERS["default"].get("CONFIG", {})
    return int(config.get("group_expiry", DEFAULT_GROUP_EXPIRY))


def _decode_presence(value: str) -> dict[str, str]:
    return json.loads(value)


async def register_category_presence(
    categoria_id: str,
    channel_name: str,
    user_id: int,
    username: str,
    role: str,
) -> tuple[list[dict[str, str]], bool]:
    key = _presence_key(categoria_id)
    user_id = str(user_id)
    presence = json.dumps(
        {"user_id": user_id, "user": username, "rol": role}
    )
    client = _redis_client()
    try:
        pipeline = client.pipeline(transaction=True)
        pipeline.hgetall(key)
        pipeline.hset(key, channel_name, presence)
        pipeline.expire(key, _group_expiry())
        existing, _, _ = await pipeline.execute()
    finally:
        await client.aclose()

    users = {}
    first_connection = True
    for value in existing.values():
        existing_presence = _decode_presence(value)
        existing_user_id = existing_presence["user_id"]
        if existing_user_id == user_id:
            first_connection = False
        else:
            users.setdefault(
                existing_user_id,
                {
                    "user": existing_presence["user"],
                    "rol": existing_presence["rol"],
                },
            )

    return list(users.values()), first_connection


async def unregister_category_presence(
    categoria_id: str,
    channel_name: str,
    user_id: int,
) -> bool:
    key = _presence_key(categoria_id)
    user_id = str(user_id)
    client = _redis_client()
    try:
        pipeline = client.pipeline(transaction=True)
        pipeline.hdel(key, channel_name)
        pipeline.hgetall(key)
        _, remaining = await pipeline.execute()
    finally:
        await client.aclose()

    return not any(
        _decode_presence(value)["user_id"] == user_id
        for value in remaining.values()
    )
