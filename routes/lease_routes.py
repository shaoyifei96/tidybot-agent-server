"""Lease management endpoints."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/lease")


class AcquireRequest(BaseModel):
    holder: str


class LeaseIdRequest(BaseModel):
    lease_id: str


def create_router(lease_mgr):
    @router.post("/acquire")
    async def acquire(req: AcquireRequest):
        return await lease_mgr.acquire(req.holder)

    @router.post("/release")
    async def release(req: LeaseIdRequest):
        return await lease_mgr.release(req.lease_id)

    @router.post("/extend")
    async def extend(req: LeaseIdRequest):
        return await lease_mgr.extend(req.lease_id)

    @router.get("/status")
    async def status():
        return lease_mgr.status()

    return router
