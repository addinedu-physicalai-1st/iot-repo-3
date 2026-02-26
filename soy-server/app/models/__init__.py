"""
SQLAlchemy ORM 모델. 마이그레이션(001~007) 스키마와 동기화.
테이블은 기존 마이그레이션으로 생성되며, ORM은 앱 레이어에서만 사용.
"""
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.utcnow()


class Base(DeclarativeBase):
    pass


class Admin(Base):
    __tablename__ = "admin"

    admin_id: Mapped[int] = mapped_column(
        "admin_id", Integer, primary_key=True, autoincrement=True
    )
    password_hash: Mapped[str] = mapped_column("password_hash", String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        "created_at", DateTime, nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        "updated_at", DateTime, nullable=False, default=_utcnow, onupdate=_utcnow
    )


class Worker(Base):
    __tablename__ = "workers"

    worker_id: Mapped[int] = mapped_column(
        "worker_id", Integer, primary_key=True, autoincrement=True
    )
    admin_id: Mapped[int] = mapped_column(
        "admin_id", Integer, ForeignKey("admin.admin_id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column("name", String(100), nullable=False)
    card_uid: Mapped[str] = mapped_column("card_uid", String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        "created_at", DateTime, nullable=False, default=_utcnow
    )


class Order(Base):
    __tablename__ = "orders"

    order_id: Mapped[int] = mapped_column(
        "order_id", Integer, primary_key=True, autoincrement=True
    )
    order_date: Mapped[datetime] = mapped_column("order_date", DateTime, nullable=False)
    status: Mapped[str] = mapped_column("status", String(20), nullable=False)

    order_items: Mapped[list["OrderItem"]] = relationship(
        "OrderItem", back_populates="order", cascade="all, delete-orphan"
    )
    inbounds: Mapped[list["Inbound"]] = relationship(
        "Inbound", back_populates="order"
    )


class OrderItem(Base):
    __tablename__ = "order_items"

    order_item_id: Mapped[int] = mapped_column(
        "order_item_id", Integer, primary_key=True, autoincrement=True
    )
    order_id: Mapped[int] = mapped_column(
        "order_id", Integer, ForeignKey("orders.order_id", ondelete="CASCADE"), nullable=False
    )
    item_code: Mapped[str] = mapped_column("item_code", String(50), nullable=False)
    expected_qty: Mapped[int] = mapped_column("expected_qty", Integer, nullable=False)

    order: Mapped["Order"] = relationship("Order", back_populates="order_items")


class Inbound(Base):
    __tablename__ = "inbounds"

    inbound_id: Mapped[str] = mapped_column("inbound_id", String(50), primary_key=True)
    order_id: Mapped[int] = mapped_column(
        "order_id", Integer, ForeignKey("orders.order_id", ondelete="RESTRICT"), nullable=False
    )
    inbound_date: Mapped[datetime] = mapped_column("inbound_date", DateTime, nullable=False)
    status: Mapped[str] = mapped_column("status", String(20), nullable=False)

    order: Mapped["Order"] = relationship("Order", back_populates="inbounds")
