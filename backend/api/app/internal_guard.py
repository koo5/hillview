"""Guard for internal-only API endpoints.

Defense-in-depth behind Caddy which already blocks /api/internal/* externally.
"""

import logging

from fastapi import HTTPException, Request, status

logger = logging.getLogger(__name__)


async def require_internal_ip(request: Request) -> None:
	"""FastAPI dependency that restricts access to direct localhost callers.

	Rejects if any proxy header is present (a direct local connection won't
	have one) or if the TCP peer is not 127.0.0.1.

	Usage:
		@router.post("/internal/foo", dependencies=[Depends(require_internal_ip)])
	"""
	if (request.headers.get("X-Forwarded-For")
		or request.headers.get("X-Real-IP")
		or request.headers.get("CF-Connecting-IP")
		or request.headers.get("X-Forwarded-Proto")
		or request.headers.get("X-Forwarded-Host")):
		logger.warning(
			f"Internal endpoint rejected: proxy headers present "
			f"(path={request.url.path})"
		)
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="Access denied",
		)

	client_ip = request.client.host if request.client else None
	if client_ip != "127.0.0.1":
		logger.warning(
			f"Internal endpoint rejected: {client_ip} is not 127.0.0.1 "
			f"(path={request.url.path})"
		)
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="Access denied",
		)
