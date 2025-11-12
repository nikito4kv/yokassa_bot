from aiogram import Router, F
from aiogram.types import ChatMemberUpdated
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.models import Subscription, SubscriptionStatus
from src.config import GROUP_ID

group_router = Router()

@group_router.chat_member(F.chat.id == int(GROUP_ID))
async def chat_member_handler(event: ChatMemberUpdated, async_session: AsyncSession) -> None:
    # Check if a new member joined and if an invite link was used
    if event.new_chat_member.status == "member" and event.invite_link:
        invite_link_url = event.invite_link.invite_link
        user_id = event.new_chat_member.user.id

        async with async_session() as session:
            # Find the subscription associated with this invite link
            subscription = await session.execute(
                select(Subscription).filter_by(invite_link=invite_link_url, user_id=user_id)
            )
            subscription = subscription.scalar_one_or_none()

            if subscription:
                # Update the subscription status to active
                subscription.status = SubscriptionStatus.active
                await session.commit()
                # Optionally, send a welcome message to the user in the group
                # await event.bot.send_message(event.chat.id, f"Welcome, {event.new_chat_member.user.full_name}! Your subscription is now active.")
            else:
                # Handle cases where the invite link doesn't match a pending subscription
                # This could be an old link, or an issue.
                # Optionally, kick the user or log the event.
                pass
