from starlette.concurrency import run_in_threadpool


async def run_sync(fn, *args, **kwargs):
    """Run a blocking call (Supabase/PostgREST, Razorpay SDK, Azure SDK, etc.)
    in Starlette's worker thread pool instead of on the event loop.

    Route handlers that mix genuine async I/O (httpx, websockets) with these
    synchronous SDK calls can't just be declared as plain `def` -- FastAPI's
    automatic threadpool dispatch only applies to the whole handler. This
    lets the blocking parts opt in individually while the rest of the
    handler keeps awaiting real async work.
    """
    return await run_in_threadpool(fn, *args, **kwargs)
