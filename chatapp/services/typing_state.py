from django.core.cache import cache


TYPING_STATE_TTL_SECONDS = 8


def _typing_cache_key(listing_id, user_a_id, user_b_id):
    low_id, high_id = sorted((int(user_a_id), int(user_b_id)))
    return f'chat:typing:{listing_id}:{low_id}:{high_id}'


def set_typing_state(listing_id, sender_id, recipient_id, is_typing):
    key = _typing_cache_key(listing_id, sender_id, recipient_id)
    state = cache.get(key, {})
    sender_key = str(sender_id)

    if is_typing:
        state[sender_key] = True
        cache.set(key, state, timeout=TYPING_STATE_TTL_SECONDS)
        return

    if sender_key in state:
        del state[sender_key]

    if state:
        cache.set(key, state, timeout=TYPING_STATE_TTL_SECONDS)
    else:
        cache.delete(key)


def is_user_typing(listing_id, sender_id, recipient_id):
    key = _typing_cache_key(listing_id, sender_id, recipient_id)
    state = cache.get(key, {})
    return bool(state.get(str(sender_id)))
