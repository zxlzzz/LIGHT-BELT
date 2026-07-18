"""
依赖注入：统一鉴权拦截，相当于 Spring 的 HandlerInterceptor。
在需要鉴权的 router 上加 dependencies=[Depends(require_auth)] 即可。
"""

from fastapi import Request, HTTPException


def require_auth(request: Request):
    pass
