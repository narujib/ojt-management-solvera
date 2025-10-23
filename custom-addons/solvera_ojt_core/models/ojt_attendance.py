# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from uuid import uuid4


class OjtAttendance(models.Model):
    _name = "ojt.attendance"
    _description = "OJT Attendance"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "check_in desc, id desc"

    # Relations: batch, event (optional), participant
    batch_id = fields.Many2one("ojt.batch", string="Batch", required=True, ondelete="cascade", index=True)
    event_link_id = fields.Many2one("ojt.event.link", string="Event", ondelete="set null", index=True)
    participant_id = fields.Many2one("ojt.participant", string="Participant", required=True, ondelete="cascade", index=True)

    # Times: check-in/out stamps
    check_in = fields.Datetime(string="Check In")
    check_out = fields.Datetime(string="Check Out")

    # Presence & method: status and capture method
    presence = fields.Selection(
        [("present", "Present"), ("late", "Late"), ("absent", "Absent")],
        string="Presence",
        required=True,
        default="absent",  # safe default; set on check-in
        tracking=True,
        help="Present/Late are counted as attended; Absent otherwise.",
    )
    method = fields.Selection(
        [("qr", "QR"), ("online", "Online"), ("manual", "Manual"), ("cron", "System")],
        string="Method",
        required=True,
        default="manual",
        help="How this attendance was captured.",
    )

    # Tokens & links: QR and join endpoints
    qr_token = fields.Char(
        string="QR Token",
        copy=False,
        index=True,
        readonly=True,
        default=lambda self: uuid4().hex,
        help="Unique token for QR/Join links.",
    )
    join_url = fields.Char(string="Join Link", compute="_compute_urls", help="Auto check-in then redirect to meeting.")
    qr_url = fields.Char(string="QR Link", compute="_compute_urls", help="Open check-in endpoint for QR.")

    # Analytics: duration and attendance percentage
    duration_minutes = fields.Float(string="Duration (minutes)", compute="_compute_duration", store=True)
    attendance_percent = fields.Float(
        string="Attendance %",
        compute="_compute_attendance_percent",
        store=True,
        group_operator="avg",
        help="100 for Present/Late, 0 for Absent.",
    )
    notes = fields.Text(string="Notes")

    _sql_constraints = [
        ("uniq_participant_event", "unique(participant_id, event_link_id)", "Attendance already exists for this participant & event."),
    ]

    # Compute: duration in minutes
    @api.depends("check_in", "check_out")
    def _compute_duration(self):
        for rec in self:
            minutes = 0.0
            if rec.check_in and rec.check_out and rec.check_out >= rec.check_in:
                delta = fields.Datetime.to_datetime(rec.check_out) - fields.Datetime.to_datetime(rec.check_in)
                minutes = round(delta.total_seconds() / 60.0, 2)
            rec.duration_minutes = max(0.0, minutes)

    # Compute: percentage flag for analytics
    @api.depends("presence")
    def _compute_attendance_percent(self):
        for rec in self:
            rec.attendance_percent = 100.0 if rec.presence in ("present", "late") else 0.0

    # Compute: public URLs from token and base
    @api.depends("qr_token")
    def _compute_urls(self):
        base = self.env["ir.config_parameter"].sudo().get_param("web.base.url", "").rstrip("/")
        for rec in self:
            token = rec.qr_token or ""
            rec.qr_url = f"{base}/ojt/q/{token}" if token else False
            rec.join_url = f"{base}/ojt/a/{token}" if token else False

    # Onchange: infer presence from check-in vs start (+grace)
    @api.onchange("check_in", "event_link_id")
    def _onchange_presence(self):
        for rec in self:
            if rec.check_in and rec.event_link_id and rec.event_link_id.date_start:
                grace = self._get_param_int("ojt_late_grace_minutes", 15)
                present_limit = rec.event_link_id.date_start
                late_limit = fields.Datetime.add(present_limit, minutes=grace)
                rec.presence = "present" if rec.check_in <= late_limit else "late"

    # Constraint: check-out must be >= check-in
    @api.constrains("check_in", "check_out")
    def _check_date_order(self):
        for rec in self:
            if rec.check_in and rec.check_out and rec.check_out < rec.check_in:
                raise ValidationError(_("Check Out cannot be earlier than Check In."))

    # Constraint: participant/event must match batch
    @api.constrains("participant_id", "batch_id", "event_link_id")
    def _check_same_batch(self):
        for rec in self:
            if rec.participant_id and rec.batch_id and rec.participant_id.batch_id != rec.batch_id:
                raise ValidationError(_("Participant must belong to the selected Batch."))
            if rec.event_link_id and rec.batch_id and rec.event_link_id.batch_id != rec.batch_id:
                raise ValidationError(_("Event must belong to the selected Batch."))

    # Action: ensure QR token exists
    def _ensure_token(self):
        for rec in self.filtered(lambda r: not r.qr_token):
            rec.qr_token = uuid4().hex

    # Action: perform check-in and set presence
    def action_check_in(self, method="manual"):
        for rec in self:
            now = fields.Datetime.now()
            if rec.check_in:
                continue
            rec._ensure_token()
            rec.method = method or "manual"
            rec.check_in = now

            presence = "present"
            if rec.event_link_id and rec.event_link_id.date_start:
                grace = self._get_param_int("ojt_late_grace_minutes", 15)
                present_limit = rec.event_link_id.date_start
                late_limit = fields.Datetime.add(present_limit, minutes=grace)
                presence = "present" if now <= late_limit else "late"
            rec.presence = presence

            rec.message_post(
                body=_("Checked in (%s). Presence: %s") % (rec.method, rec.presence),
                subtype_xmlid="mail.mt_note",
            )

    # Action: perform check-out and log note
    def action_check_out(self, method="manual"):
        for rec in self:
            if not rec.check_in or rec.check_out:
                continue
            rec.method = method or rec.method or "manual"
            rec.check_out = fields.Datetime.now()
            rec.message_post(body=_("Checked out (%s).") % rec.method, subtype_xmlid="mail.mt_note")

    # Cron: mark as absent after start + threshold if not checked in
    @api.model
    def _cron_mark_absent(self):
        """Set presence to 'absent' after start + buffer when no check-in."""
        after = self._get_param_int("ojt_auto_absent_after_minutes", 45)
        now = fields.Datetime.now()
        Attendance = self.env["ojt.attendance"].sudo()
        domain = [
            ("check_in", "=", False),
            ("presence", "!=", "absent"),
            ("event_link_id.date_start", "!=", False),
            ("event_link_id.date_start", "<=", fields.Datetime.subtract(now, minutes=after)),
        ]
        records = Attendance.search(domain, limit=1000)
        for rec in records:
            rec.write({"presence": "absent", "method": "cron"})
            rec.message_post(body=_("Auto-marked Absent by system."), subtype_xmlid="mail.mt_note")

    # Cron: auto checkout at event end + buffer
    @api.model
    def _cron_auto_checkout(self):
        """Checkout attendees at event end + buffer when still open."""
        buf = self._get_param_int("ojt_auto_checkout_buffer_minutes", 5)
        now = fields.Datetime.now()
        Attendance = self.env["ojt.attendance"].sudo()
        domain = [
            ("check_in", "!=", False),
            ("check_out", "=", False),
            ("event_link_id.date_end", "!=", False),
            ("event_link_id.date_end", "<=", fields.Datetime.subtract(now, minutes=buf)),
        ]
        records = Attendance.search(domain, limit=1000)
        for rec in records:
            rec.write({"check_out": rec.event_link_id.date_end, "method": rec.method or "cron"})
            rec.message_post(body=_("Auto check-out by system."), subtype_xmlid="mail.mt_note")

    # Util: read int parameter safely
    @api.model
    def _get_param_int(self, key, default):
        icp = self.env["ir.config_parameter"].sudo()
        try:
            return int(icp.get_param(key, default))
        except Exception:
            return int(default)
