import os
import time
import uuid
from collections import defaultdict, deque

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware

EMAIL = os.getenv("ASSIGNMENT_EMAIL", "23f2002788@ds.study.iitm.ac.in")

ALLOWED_ORIGINS = [
    "https://app-wq3ync.example.com",   # your assigned origin
    "https://exam.sanand.workers.dev",  # exam page origin (verify in Step 5!)
]
extra = os.getenv("EXAM_ORIGIN")
if extra and extra not in ALLOWED_ORIGINS:
    ALLOWED_ORIGINS.append(extra)

BUCKET_SIZE = 14
WINDOW_SECONDS = 10

app = FastAPI()


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.requests = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS":
            return await call_next(request)

        client_id = request.headers.get("X-Client-Id", "anonymous")
        now = time.monotonic()
        bucket = self.requests[client_id]

        while bucket and now - bucket[0] >= WINDOW_SECONDS:
            bucket.popleft()

        if len(bucket) >= BUCKET_SIZE:
            retry_after = max(1, int(WINDOW_SECONDS - (now - bucket[0]) + 0.999))
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded"},
                headers={"Retry-After": str(retry_after)},
            )

        bucket.append(now)
        return await call_next(request)


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


# ORDER MATTERS: last added = outermost door.
# Walk-in order will be: CORS -> RequestContext -> RateLimit -> endpoint
app.add_middleware(RateLimitMiddleware)        # innermost
app.add_middleware(RequestContextMiddleware)   # middle
app.add_middleware(                            # outermost (added LAST)
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "Retry-After"],
)


@app.get("/ping")
async def ping(request: Request):
    return {"email": EMAIL, "request_id": request.state.request_id}