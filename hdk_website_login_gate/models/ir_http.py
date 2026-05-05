# -*- coding: utf-8 -*-
#################################################################################
# Author: Hamdek
# Copyright(c): 2026-TODAY Hamdek
# All Rights Reserved.
#
# License: OPL-1 (Odoo Proprietary License v1.0)
#################################################################################

import werkzeug.exceptions

from odoo import models
from odoo.http import request


# Prefixes allowed for guests when full-site login is on (path fallback only).
_HDK_PUBLIC_SITE_PREFIXES = (
    "/web/signup",
    "/web/reset_password",
    "/payment",
)


def _hdk_normalize_frontend_path(path):
    """Strip an optional /<url_code>/ prefix when it matches installed website languages."""
    path = path or "/"
    if not path.startswith("/"):
        path = "/" + path
    path = path.rstrip("/") or "/"
    segments = [s for s in path.split("/") if s]
    if not segments:
        return "/"
    url_codes = set()
    try:
        frontend_langs = request.env["res.lang"].sudo()._get_frontend()
        url_codes.update(info.url_code for info in frontend_langs.values())
    except Exception:
        pass
    req_lang = getattr(request, "lang", None)
    if req_lang:
        url_codes.add(req_lang.url_code)
    if segments[0] in url_codes:
        segments = segments[1:]
    return "/" + "/".join(segments) if segments else "/"


def _hdk_path_allowed_under_site_lock(path):
    """Fallback when no matched route flag (e.g. some fallbacks): allow login & auth URLs."""
    raw = (path or "/").rstrip("/") or "/"
    norm = _hdk_normalize_frontend_path(path)
    for candidate in (raw, norm):
        if candidate == "/web/login" or candidate.startswith("/web/login/"):
            return True
        for prefix in _HDK_PUBLIC_SITE_PREFIXES:
            if candidate == prefix or candidate.startswith(prefix + "/"):
                return True
    return False


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    @classmethod
    def _hdk_endpoint_public_under_site_lock(cls, endpoint):
        """True if this HTTP endpoint must stay reachable for anonymous users."""
        routing = getattr(endpoint, "routing", None) or {}
        for path in routing.get("routes") or ():
            if not isinstance(path, str):
                continue
            p = path.rstrip("/") or "/"
            if p == "/web/login" or p.startswith("/web/login/"):
                return True
            if p.startswith("/web/signup"):
                return True
            if p.startswith("/web/reset_password"):
                return True
            if p == "/payment" or p.startswith("/payment/"):
                return True
        name = getattr(endpoint, "__name__", "") or ""
        if name in (
            "web_login",
            "web_totp",
            "web_auth_signup",
            "web_auth_reset_password",
            "display_status",
            "poll_status",
            "payment_pay",
            "payment_confirm",
        ):
            return True
        return False

    @classmethod
    def _pre_dispatch(cls, rule, arguments):
        # Set before super(): http_routing._pre_dispatch calls _frontend_pre_dispatch inside super chain.
        request.hdk_site_lock_route_public = cls._hdk_endpoint_public_under_site_lock(rule.endpoint)
        super()._pre_dispatch(rule, arguments)

    @classmethod
    def _frontend_pre_dispatch(cls):
        super()._frontend_pre_dispatch()
        website = getattr(request, "website", None)
        if not website or not website.hdk_login_required_website:
            return
        if not request.env.user._is_public():
            return
        if getattr(request, "hdk_site_lock_route_public", False):
            return
        path = request.httprequest.path or "/"
        if _hdk_path_allowed_under_site_lock(path):
            return
        werkzeug.exceptions.abort(
            request.redirect_query(
                "/web/login",
                query={"redirect": request.httprequest.full_path},
                code=303,
            )
        )
