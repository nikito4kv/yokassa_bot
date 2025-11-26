from sqlalchemy import BigInteger, DECIMAL, TIMESTAMP, Enum, ForeignKey, Integer, Date
from sqlalchemy.orm import Mapped, mapped_column
from src.database import Base
import enum
import datetime
import decimal

class User(Base):
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    full_name: Mapped[str]
    username: Mapped[str | None]

class SubscriptionStatus(enum.Enum):
    active = "active"
    expired = "expired"
    pending = "pending"

class Subscription(Base):
    __tablename__ = 'subscriptions'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('users.telegram_id'))
    end_date: Mapped[datetime.datetime] = mapped_column(TIMESTAMP)
    status: Mapped[SubscriptionStatus] = mapped_column(Enum(SubscriptionStatus))
    amount_paid: Mapped[decimal.Decimal] = mapped_column(DECIMAL)
    start_date: Mapped[datetime.datetime] = mapped_column(TIMESTAMP)
    invite_link: Mapped[str | None]
    last_warning_sent: Mapped[datetime.date | None] = mapped_column(Date)

class PaymentStatus(enum.Enum):
    succeeded = "succeeded"
    pending = "pending"
    manual_review = "manual_review"
    rejected = "rejected"

class Payment(Base):
    __tablename__ = 'payments'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    yookassa_id: Mapped[str | None] = mapped_column(nullable=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('users.telegram_id'))
    status: Mapped[PaymentStatus] = mapped_column(Enum(PaymentStatus))
    subscription_id: Mapped[int] = mapped_column(Integer, ForeignKey('subscriptions.id'))
    bot_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

class SystemSettings(Base):
    __tablename__ = 'system_settings'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    manual_payment_enabled: Mapped[bool] = mapped_column(default=False)

class ManualPayment(Base):
    __tablename__ = 'manual_payments'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('users.telegram_id'))
    photo_id: Mapped[str]
    created_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, default=datetime.datetime.utcnow)
    verified_at: Mapped[datetime.datetime | None] = mapped_column(TIMESTAMP, nullable=True)
    verified_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

