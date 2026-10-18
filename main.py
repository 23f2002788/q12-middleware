import os
import time
import uuid
from collections import defaultdict, deque

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware


# --------------------------------------------------
# Configuration
# --------------------------------------------------

EMAIL = os.getenv("ASSIGNMENT_EMAIL", "23f2002788@ds.study.iitm.ac.in")

ALLOWED_ORIGINS = [
    "https://app-wq3ync.example.com",
    "https://exam.sanand.workers.dev",
]

# Add the exact exam page origin here when known.
# Alternatively, set EXAM_ORIGIN as an environment variable.
exam_origin = os.getenv("EXAM_ORIGIN")
if exam_origin and exam_origin not in ALLOWED_ORIGINS:
    ALLOWED_ORIGINS.append(exam_origin)

BUCKET_SIZE = 14
WINDOW_SECONDS = 10

app = FastAPI()


# --------------------------------------------------
# Middleware 1: Per-client rate limiting
# --------------------------------------------------

class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.requests = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        # CORS preflight requests should not consume a bucket.
        if request.method == "OPTIONS":
            return await call_next(request)

        client_id = request.headers.get("X-Client-Id", "anonymous")
        now = time.monotonic()

        bucket = self.requests[client_id]

        # Remove requests that are outside the 10-second window.
        while bucket and now - bucket[0] >= WINDOW_SECONDS:
            bucket.popleft()

        # The client has already used all 14 requests.
        if len(bucket) >= BUCKET_SIZE:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded"},
            )

        bucket.append(now)
        return await call_next(request)


# --------------------------------------------------
# Middleware 2: CORS
# --------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["X-Request-ID", "X-Client-Id"],
)


# --------------------------------------------------
# Middleware 3: Request context
# --------------------------------------------------

class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID")

        if not request_id:
            request_id = str(uuid.uuid4())

        request.state.request_id = request_id

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id

        return response

# Middleware order matters: the last added is outermost.
app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestContextMiddleware)


# --------------------------------------------------
# Endpoint: GET /ping
# --------------------------------------------------

@app.get("/ping")
async def ping(request: Request):
    return {
        "email": EMAIL,
        "request_id": request.state.request_id,
    }
