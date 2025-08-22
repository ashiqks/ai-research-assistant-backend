from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, JSON, func
from sqlalchemy.orm import relationship
from .base import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    auth0_sub = Column(String(255), unique=True, index=True, nullable=False)
    email = Column(String(320), index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Session(Base):
    __tablename__ = "sessions"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    title = Column(String(255))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class ResearchRun(Base):
    __tablename__ = "research_runs"
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("sessions.id", ondelete="CASCADE"), index=True, nullable=False)
    status = Column(String(50), default="pending")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True))

class RunEvent(Base):
    __tablename__ = "run_events"
    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("research_runs.id", ondelete="CASCADE"), index=True, nullable=False)
    type = Column(String(50))
    payload = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Memory(Base):
    __tablename__ = "memories"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    content = Column(Text, nullable=False)
    meta = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Artifact(Base):
    __tablename__ = "artifacts"
    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("research_runs.id", ondelete="CASCADE"), index=True, nullable=False)
    kind = Column(String(50))
    uri = Column(String(1024))
    meta = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

