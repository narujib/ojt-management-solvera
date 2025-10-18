# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class OjtAttendance(models.Model):
    _name = "ojt.attendance"
    _description = "OJT Attendance"
    _order = "check_in desc, id desc"

    # Relasi utama
    batch_id = fields.Many2one(
        "ojt.batch", string="Batch", required=True, ondelete="cascade", index=True
    )
    event_link_id = fields.Many2one(
        "ojt.event.link", string="Event", ondelete="set null", index=True
    )
    participant_id = fields.Many2one(
        "ojt.participant", string="Participant", required=True, ondelete="cascade", index=True
    )

    # Waktu
    check_in = fields.Datetime(string="Check In")
    check_out = fields.Datetime(string="Check Out")

    # Status kehadiran & metode
    presence = fields.Selection(
        [("present", "Present"), ("late", "Late"), ("absent", "Absent")],
        string="Presence", required=True, default="present", tracking=True,
    )
    method = fields.Selection(
        [("qr", "QR"), ("online", "Online"), ("manual", "Manual")],
        string="Method", required=True, default="manual",
    )

    # Durasi (menit)
    duration_minutes = fields.Float(
        string="Duration (minutes)",
        compute="_compute_duration", store=True
    )

    # Catatan
    notes = fields.Text(string="Notes")

    # ---------- Compute ----------
    @api.depends("check_in", "check_out")
    def _compute_duration(self):
        for rec in self:
            minutes = 0.0
            if rec.check_in and rec.check_out and rec.check_out >= rec.check_in:
                delta = fields.Datetime.to_datetime(rec.check_out) - fields.Datetime.to_datetime(rec.check_in)
                minutes = round(delta.total_seconds() / 60.0, 2)
            rec.duration_minutes = max(0.0, minutes)

    # ---------- Onchange bantu (opsional) ----------
    @api.onchange("check_in", "event_link_id")
    def _onchange_presence(self):
        for rec in self:
            # Heuristik sederhana: late jika check_in > event start
            if rec.check_in and rec.event_link_id and rec.event_link_id.date_start:
                rec.presence = "late" if rec.check_in > rec.event_link_id.date_start else "present"

    # ---------- Validasi ----------
    @api.constrains("check_in", "check_out")
    def _check_date_order(self):
        for rec in self:
            if rec.check_in and rec.check_out and rec.check_out < rec.check_in:
                raise ValidationError(_("Check Out cannot be earlier than Check In."))

    @api.constrains("participant_id", "batch_id", "event_link_id")
    def _check_same_batch(self):
        for rec in self:
            if rec.participant_id and rec.batch_id and rec.participant_id.batch_id != rec.batch_id:
                raise ValidationError(_("Participant must belong to the selected Batch."))
            if rec.event_link_id and rec.batch_id and rec.event_link_id.batch_id != rec.batch_id:
                raise ValidationError(_("Event must belong to the selected Batch."))
