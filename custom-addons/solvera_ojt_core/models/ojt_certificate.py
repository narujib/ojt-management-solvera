# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
import uuid


class OjtCertificate(models.Model):
    _name = "ojt.certificate"
    _description = "OJT Certificate"
    _order = "issued_on desc, id desc"
    _rec_name = "name"

    # Identity
    name = fields.Char(string="Certificate Title", required=True, index=True)
    serial_number = fields.Char(string="Serial Number", copy=False, index=True)
    qr_token = fields.Char(string="QR Token", copy=False, index=True)

    # Relations
    batch_id = fields.Many2one("ojt.batch", string="Batch", required=True, ondelete="cascade", index=True)
    participant_id = fields.Many2one("ojt.participant", string="Participant", required=True, ondelete="cascade", index=True)
    partner_id = fields.Many2one("res.partner", string="Partner", related="participant_id.partner_id", store=False, readonly=True)

    # Values
    issued_on = fields.Date(string="Issued On")
    attendance_rate = fields.Float(string="Attendance Rate")
    final_score = fields.Float(string="Final Score")
    grade = fields.Selection([("A", "A"), ("B", "B"), ("C", "C")], string="Grade")
    pdf_report = fields.Binary(string="PDF Report", attachment=True)
    notes = fields.Text(string="Notes")

    # State
    state = fields.Selection(
        [("draft", "Draft"), ("issued", "Issued"), ("revoked", "Revoked")],
        string="State", default="draft", tracking=True, required=True
    )

    # ---------- Constraints ----------
    _sql_constraints = [
        ("uniq_serial", "unique(serial_number)", "Serial Number must be unique."),
        ("uniq_qr_token", "unique(qr_token)", "QR Token must be unique."),
        ("uniq_participant_batch", "unique(participant_id, batch_id)", "Certificate must be unique per Participant and Batch."),
    ]

    @api.constrains("attendance_rate", "final_score")
    def _check_ranges(self):
        for rec in self:
            for val, label in [(rec.attendance_rate, _("Attendance Rate")), (rec.final_score, _("Final Score"))]:
                if val is not None and (val < 0.0 or val > 100.0):
                    raise ValidationError(_("%s must be within 0..100.") % label)

    @api.constrains("participant_id", "batch_id")
    def _check_same_batch(self):
        for rec in self:
            if rec.participant_id and rec.batch_id and rec.participant_id.batch_id != rec.batch_id:
                raise ValidationError(_("Participant must belong to the selected Batch."))

    # ---------- Helpers ----------
    def _ensure_serial_and_token(self):
        """Fill serial_number via sequence & qr_token via UUID if missing."""
        seq = self.env["ir.sequence"]
        for rec in self:
            if not rec.serial_number:
                rec.serial_number = seq.next_by_code("ojt.certificate.seq") or False
            if not rec.qr_token:
                rec.qr_token = uuid.uuid4().hex

    def _default_scores_from_participant(self):
        for rec in self:
            if rec.participant_id:
                if rec.attendance_rate in (None, 0.0):
                    rec.attendance_rate = rec.participant_id.attendance_rate or 0.0
                if rec.final_score in (None, 0.0):
                    rec.final_score = rec.participant_id.final_score or 0.0
            # simple grading: A >= 85, B >= 70 else C
            if not rec.grade:
                if (rec.final_score or 0.0) >= 85.0:
                    rec.grade = "A"
                elif (rec.final_score or 0.0) >= 70.0:
                    rec.grade = "B"
                else:
                    rec.grade = "C"

    # ---------- Actions ----------
    def action_issue(self):
        for rec in self:
            rec._default_scores_from_participant()
            rec._ensure_serial_and_token()
            if not rec.issued_on:
                rec.issued_on = fields.Date.context_today(self)
            rec.state = "issued"

    def action_revoke(self):
        self.write({"state": "revoked"})

    def action_reset_draft(self):
        self.write({"state": "draft"})
