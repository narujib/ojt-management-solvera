# -*- coding: utf-8 -*-
from odoo import http, fields
from odoo.http import request
from urllib.parse import quote as url_quote


# Helper: normalize http(s) URLs (prepend https:// when scheme missing)
def _normalize_http_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    if "://" in url:
        return url
    return "https://" + url


# Helper: make absolute URL relative to current host
def _make_absolute(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    if "://" in url:
        return url
    base = request.httprequest.host_url.rstrip("/")
    if url.startswith("/"):
        return f"{base}{url}"
    return f"{base}/{url}"


class OjtAttendancePublic(http.Controller):
    # Helper: enforce check-in time window and return (ok, message)
    def _check_window_and_message(self, att):
        icp = request.env["ir.config_parameter"].sudo()
        try:
            early = int(icp.get_param("ojt_early_checkin_open_minutes", 15))
        except Exception:
            early = 15
        try:
            close = int(icp.get_param("ojt_close_checkin_after_end_minutes", 0))
        except Exception:
            close = 0

        now = fields.Datetime.now()
        start = att.event_link_id.date_start
        end = att.event_link_id.date_end
        open_from = fields.Datetime.subtract(start, minutes=early) if start else None
        close_at = fields.Datetime.add(end, minutes=close) if end else None

        if open_from and now < open_from:
            return (False, "Check-in opens at %s" % (start or "scheduled time"))
        if close_at and now > close_at:
            return (False, "Session closed. Check-in is no longer available.")
        return (True, "")

    # Helper: client-side redirect page (meta + JS)
    def _external_redirect(self, url: str):
        url = _normalize_http_url(url)
        if not url:
            return request.render("solvera_ojt_core.portal_ojt_join_info", {})
        return request.render("solvera_ojt_core.portal_ojt_redirect", {"target_url": url})

    # Route: QR check-in (renders confirmation)
    @http.route(["/ojt/q/<string:token>"], type="http", auth="public", website=True, csrf=False, sitemap=False)
    def ojt_qr_check(self, token=None, **kw):
        Att = request.env["ojt.attendance"].sudo()
        att = Att.search([("qr_token", "=", token)], limit=1)
        if not att:
            return request.not_found()

        ok, msg = self._check_window_and_message(att)
        if not ok:
            return request.render("solvera_ojt_core.portal_ojt_qr_success", {"message": msg})

        if not att.check_in:
            att.action_check_in(method="qr")
        return request.render("solvera_ojt_core.portal_ojt_qr_success", {"message": "Check-in recorded."})

    # Route: auto check-in then redirect to meeting (via client redirect)
    @http.route(["/ojt/a/<string:token>"], type="http", auth="public", website=True, csrf=False, sitemap=False)
    def ojt_join_auto_check(self, token=None, **kw):
        Att = request.env["ojt.attendance"].sudo()
        att = Att.search([("qr_token", "=", token)], limit=1)
        if not att:
            return request.not_found()

        ok, msg = self._check_window_and_message(att)
        if not ok:
            return request.render("solvera_ojt_core.portal_ojt_qr_success", {"message": msg})

        if not att.check_in:
            att.action_check_in(method="online")

        meeting = att.event_link_id.online_meeting_url or ""
        return self._external_redirect(meeting)

    # Route: QR image (canvas by default; server barcode engine optional)
    @http.route(["/ojt/qrimg/<string:token>"], type="http", auth="public", website=True, csrf=False, sitemap=False)
    def ojt_qr_image(self, token, **kw):
        """
        Show QR using client canvas or server engine.
        /ojt/qrimg/<token>?mode=join|checkin[&engine=client|server]
        """
        mode = (kw.get("mode") or "join").lower()
        engine = (kw.get("engine") or "client").lower()

        Att = request.env["ojt.attendance"].sudo()
        att = Att.search([("qr_token", "=", token)], limit=1)
        if not att:
            return request.not_found()

        src = att.join_url if mode == "join" else att.qr_url
        if not src:
            return request.not_found()

        if mode == "join":
            src = _normalize_http_url(src)

        if engine == "server":
            try:
                encoded = url_quote(src, safe="")
                qr_path = f"/report/barcode?type=QR&value={encoded}&width=512&height=512"
                return request.redirect(qr_path, code=302)
            except Exception:
                pass  # fallback to client

        return request.render("solvera_ojt_core.portal_ojt_qr_client", {"qr_value": src})

    # Route: QR PNG generator page (client-side)
    @http.route(["/ojt/qrpng/<string:token>"], type="http", auth="public", website=True, csrf=False, sitemap=False)
    def ojt_qr_png(self, token, **kw):
        """Render QR as PNG via client JS. mode=checkin|join (default: checkin)."""
        mode = (kw.get("mode") or "checkin").lower()

        Att = request.env["ojt.attendance"].sudo()
        att = Att.search([("qr_token", "=", token)], limit=1)
        if not att:
            return request.not_found()

        if mode == "join":
            src = _normalize_http_url(att.join_url or "")
        else:
            src = _make_absolute(att.qr_url or "")

        if not src:
            return request.not_found()

        return request.render("solvera_ojt_core.portal_ojt_qr_png", {"qr_value": src})
