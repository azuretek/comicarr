#  Copyright (C) 2025–2026 Comicarr contributors
#
#  This file is part of Comicarr.
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""
FastAPI application — lifespan, router composition, static file serving.
"""

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles

from comicarr.app.core.events import EventBus
from comicarr.app.core.exceptions import register_exception_handlers
from comicarr.app.core.middleware import (
    CSRFMiddleware,
    SecurityHeadersMiddleware,
    SetupGateMiddleware,
)
from comicarr.app.core.runtime import get_runtime, set_runtime_acquisition_status, set_runtime_field

# Bounded worker-drain timeout for the authoritative lifespan shutdown drain.
# The legacy ad-hoc value was pool.join(5) which is almost certainly too short
# for a multi-file post-processing run. 30s is a conservative default; the
# exact value is TUNABLE against the measured worst-case PP duration on the
# NAS deployment. Regardless of this value, the terminal non-blocking
# hard-kill backstop in comicarr.shutdown() guarantees the process exits.
SHUTDOWN_DRAIN_TIMEOUT = 30.0

# All pipeline worker pools. The bounded join below is RELOCATED here from
# queue_schedule()'s shutdown branch so the FastAPI lifespan is the single
# authoritative drain. MASS_ADD and MASS_REFRESH are on-demand but still own
# database work and must not outlive engine disposal.
_WORKER_POOLS = ("SNPOOL", "NZBPOOL", "SEARCHPOOL", "PPPOOL", "DDLPOOL", "MASS_ADD", "MASS_REFRESH")
_CONTEXT_POOL_FIELDS = {
    "SNPOOL": "sn_pool",
    "NZBPOOL": "nzb_pool",
    "SEARCHPOOL": "search_pool",
    "PPPOOL": "pp_pool",
    "DDLPOOL": "ddl_pool",
    "MASS_ADD": "mass_add_pool",
    "MASS_REFRESH": "mass_refresh_pool",
}


def _drain_worker_pools(timeout, ctx=None):
    """Bounded join of every live worker pool — runs OFF the event loop.

    Relocated from queue_schedule()'s shutdown branch. Each pool gets a
    bounded ``join(timeout)``; an unjoined pool is left for the terminal
    hard-kill backstop (a worker wedged in native code must never hang
    termination forever). An AssertionError from a join is swallowed here so
    it can NOT short-circuit past the journal flush + engine.dispose() (the
    removed ``except AssertionError: os._exit(0)`` landmine).
    """
    import comicarr
    from comicarr import logger

    # Shared monotonic deadline so the TOTAL drain is bounded by ``timeout``,
    # not ``timeout * len(_WORKER_POOLS)``. Each pool gets only the time
    # remaining until the deadline; once exhausted, remaining pools are left
    # for the terminal hard-kill backstop.
    deadline = time.monotonic() + timeout

    for pool_attr in _WORKER_POOLS:
        pool = getattr(ctx, _CONTEXT_POOL_FIELDS[pool_attr], None) if ctx is not None else None
        if pool is None:
            # Pre-factory legacy tests and the remaining bootstrap bridge use
            # the same pool objects through these aliases.
            pool = getattr(comicarr, pool_attr, None)
        if pool is None:
            continue
        try:
            if pool.is_alive() is False:
                continue
        except Exception as e:
            logger.fdebug("[SHUTDOWN] pool.is_alive() check failed for %s: %s" % (pool_attr, e))
            continue
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            logger.warn("[SHUTDOWN] Drain deadline exhausted; leaving %s for hard-kill backstop" % pool_attr)
            continue
        try:
            pool.join(remaining)
            logger.fdebug("[SHUTDOWN] Drained worker pool %s" % pool_attr)
        except AssertionError as e:
            # Must NOT short-circuit the drain — just log and continue so the
            # journal flush + engine.dispose() still run.
            logger.warn("[SHUTDOWN] AssertionError joining %s: %s" % (pool_attr, e))
        except Exception as e:
            logger.error("[SHUTDOWN] Error joining %s: %s" % (pool_attr, e))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan — startup and shutdown."""
    loop = asyncio.get_running_loop()
    executor = ThreadPoolExecutor(max_workers=20)
    loop.set_default_executor(executor)

    # Worker bootstrap creates the only process runtime. Lifespan attaches it
    # to FastAPI; rebuilding a context here would fork queue/lock/set state.
    ctx = get_runtime()

    event_bus = ctx.event_bus or EventBus()
    event_bus.set_loop(loop)
    ctx.event_bus = event_bus

    app.state.ctx = ctx

    # Re-read the durable acquisition fence in the serving process. This never
    # prevents FastAPI startup: authenticated diagnostics need to explain a
    # fail-closed schema or interrupted repair while workers remain stopped.
    try:
        from comicarr.app.acquisition.maintenance import refresh_runtime_state

        app.state.acquisition_maintenance = refresh_runtime_state(ctx.config).as_dict()
    except Exception:
        import comicarr

        set_runtime_acquisition_status(
            workers_blocked=True,
            block_reason="maintenance_gate_unavailable",
        )
        app.state.acquisition_maintenance = {
            "blocked": True,
            "reason": "maintenance_gate_unavailable",
            "schema_ready": bool(getattr(comicarr, "ACQUISITION_SCHEMA_READY", False)),
        }

    from comicarr import logger

    yield

    import comicarr
    from comicarr import logger

    logger.info("[SHUTDOWN] FastAPI lifespan shutdown starting...")

    # ---- Single authoritative ordered drain (U7) -------------------------
    # The FastAPI lifespan is now the ONE place the clean shutdown drain
    # happens. The legacy second path (Comicarr.py -> shutdown() -> halt() ->
    # queue_schedule drain) is reduced to signalling + the terminal branch.
    # Order is load-bearing:
    #   1. scheduler.shutdown(wait=False)  — stop new pipeline work
    #   2. q.put('exit') for all 5 queues  — stop intake
    #   3. bounded pool.join OFF the loop, on a DEDICATED executor
    #      (== final journal flush: workers write the journal synchronously
    #       via the façade, so "drain workers fully" IS the flush guarantee)
    #   4. ai/cv client close
    #   5. engine.dispose()                — strictly AFTER the drain
    #   6. executor / drain-executor shutdown — AFTER the drain
    #   7. default SIGNAL only if unset (never clobber restart/update/maint)

    # 1. Stop accepting new scheduled pipeline work.
    if ctx.scheduler:
        try:
            ctx.scheduler.shutdown(wait=False)
            logger.info("[SHUTDOWN] APScheduler stopped")
        except Exception as e:
            logger.error("[SHUTDOWN] Error stopping scheduler: %s" % e)

    # 2. Signal every worker queue to stop intake. Workers finish their current
    #    item, then exit on the sentinel.
    for q in [
        ctx.snatched_queue,
        ctx.nzb_queue,
        ctx.pp_queue,
        ctx.search_queue,
        ctx.ddl_queue,
        # MASS_ADD reads ADD_LIST as its shutdown sentinel. ISSUE_WATCH_LIST
        # carries real issue IDs, so it is drained rather than poisoned with a
        # value that could be treated as an issue during an in-flight loop.
        ctx.add_list,
        ctx.refresh_queue,
    ]:
        try:
            q.put("exit")
        except Exception:
            pass

    # 3. Bounded worker drain — relocated here from queue_schedule's shutdown
    #    branch. pool.join(timeout) BLOCKS, so it runs off the event loop on a
    #    DEDICATED single-thread executor. It must NOT be scheduled onto
    #    `executor` (the lifespan's default executor) because that is torn
    #    down below; a dedicated executor keeps the drain independent of that
    #    teardown. This MUST complete before engine.dispose() so an in-flight
    #    worker journal write never hits a disposed engine (R7/R8/AE5).
    drain_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="shutdown-drain")
    try:
        await loop.run_in_executor(drain_executor, _drain_worker_pools, SHUTDOWN_DRAIN_TIMEOUT, ctx)
        logger.info("[SHUTDOWN] Worker drain complete")
    except Exception as e:
        logger.error("[SHUTDOWN] Error during worker drain: %s" % e)

    # 4. Close async/sync external clients (workers are drained now).
    if ctx.ai_async_client:
        try:
            await ctx.ai_async_client.close()
            logger.info("[SHUTDOWN] AI async client closed")
        except Exception as e:
            logger.error("[SHUTDOWN] Error closing AI client: %s" % e)

    if ctx.ai_client:
        try:
            ctx.ai_client.close()
            logger.info("[SHUTDOWN] AI sync client closed")
        except Exception as e:
            logger.error("[SHUTDOWN] Error closing AI sync client: %s" % e)

    if ctx.cv_session:
        try:
            ctx.cv_session.close()
            logger.info("[SHUTDOWN] CV session closed")
        except Exception:
            pass

    # 5. Dispose the DB engine — strictly AFTER the bounded drain so the
    #    drained workers' synchronous journal writes have all landed.
    try:
        from comicarr import db

        engine = db.get_engine()
        if engine:
            engine.dispose()
            logger.info("[SHUTDOWN] Database engine disposed")
    except Exception as e:
        logger.error("[SHUTDOWN] Error disposing database: %s" % e)

    # 6. Tear down executors — AFTER the drain (the drain used a dedicated
    #    executor, never `executor`, so this order is safe).
    try:
        drain_executor.shutdown(wait=False)
    except Exception as e:
        logger.error("[SHUTDOWN] Error shutting down drain executor: %s" % e)

    try:
        executor.shutdown(wait=False)
        logger.info("[SHUTDOWN] ThreadPoolExecutor shut down")
    except Exception as e:
        logger.error("[SHUTDOWN] Error shutting down executor: %s" % e)

    # 7. Default the signal ONLY if nothing else set it. Guarding with
    #    `if not comicarr.SIGNAL:` preserves restart/update/maintenance
    #    intent (documented prior regression: an unconditional write here
    #    made restart indistinguishable from shutdown).
    signal = comicarr.SIGNAL or ctx.signal or "shutdown"
    set_runtime_field(ctx, "signal", signal)
    set_runtime_field(ctx, "disposed", True, project_legacy=False)

    logger.info("[SHUTDOWN] FastAPI lifespan shutdown complete")


def create_app():
    """Factory function — creates and configures the FastAPI application."""
    app = FastAPI(
        title="Comicarr",
        description="Automated Comic Book Manager",
        lifespan=lifespan,
    )

    app.add_middleware(SetupGateMiddleware)
    app.add_middleware(CSRFMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)

    register_exception_handlers(app)

    @app.get("/api/health")
    async def health_check():
        return JSONResponse(content={"status": "ok"})

    from comicarr.app.ai.router import router as ai_router
    from comicarr.app.dashboard.router import router as dashboard_router
    from comicarr.app.downloads.router import router as downloads_router
    from comicarr.app.metadata.router import router as metadata_router
    from comicarr.app.opds.router import router as opds_router
    from comicarr.app.search.router import router as search_router
    from comicarr.app.series.router import router as series_router
    from comicarr.app.storyarcs.router import router as storyarcs_router
    from comicarr.app.system.router import router as system_router
    from comicarr.app.weekly.router import router as weekly_router

    app.include_router(system_router)
    app.include_router(ai_router)
    app.include_router(dashboard_router)
    app.include_router(weekly_router)
    app.include_router(metadata_router)
    app.include_router(storyarcs_router)
    app.include_router(series_router)
    app.include_router(search_router)
    app.include_router(downloads_router)
    app.include_router(opds_router)

    frontend_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
    if frontend_dist.is_dir():

        class CachedStaticFiles(StaticFiles):
            async def get_response(self, path, scope):
                try:
                    response = await super().get_response(path, scope)
                except HTTPException as ex:
                    if ex.status_code == 404:
                        # SPA fallback: serve index.html so React Router
                        # handles client-side routes like /settings, /login
                        response = await super().get_response("index.html", scope)
                        response.headers["Cache-Control"] = "no-cache"
                        return response
                    raise
                if path.startswith("assets/"):
                    response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
                else:
                    response.headers["Cache-Control"] = "no-cache"
                return response

        app.mount("/", CachedStaticFiles(directory=str(frontend_dist), html=True), name="frontend")

    return app


app = create_app()
