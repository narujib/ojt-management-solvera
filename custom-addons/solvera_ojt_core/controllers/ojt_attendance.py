# -*- coding: utf-8 -*-
from odoo import http, fields  # fields used for datetime helpers
from odoo.http import request


class OjtAttendancePublic(http.Controller):
    # Helper: enforce check-in window based on event and config
    def _check_window_and_message(self, att):
        """Return (ok, message). When ok=False, block check-in and show message."""
        icp = request.env["ir.config_parameter"].sudo()

        # Config: minutes before start allowed; minutes after end allowed
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

    # Route: QR-based check-in (renders confirmation)
    @http.route(
        ["/ojt/q/<string:token>"],
        type="http",
        auth="public",
        website=True,
        csrf=False,
        sitemap=False,
    )
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

    # Route: auto check-in then redirect to meeting (if available)
    @http.route(
        ["/ojt/a/<string:token>"],
        type="http",
        auth="public",
        website=True,
        csrf=False,
        sitemap=False,
    )
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
        if meeting:
            return request.redirect(meeting, code=302)

        return request.render("solvera_ojt_core.portal_ojt_join_info", {})
