def referral_link(user_id: int) -> str:
    """
    Generates a Telegram referral link for a given user ID.

    Args:
        user_id (int): The Telegram user ID of the referrer.

    Returns:
        str: A referral link that embeds the user's ID in the start parameter.
    """
    bot_username = "AradaBingoBot"  # Replace with your actual bot username
    return f"https://t.me/{bot_username}?start={user_id}"

