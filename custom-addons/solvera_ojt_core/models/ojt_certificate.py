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

    # Values (readonly: diisi otomatis saat Issue)
    issued_on = fields.Date(string="Issued On")
    attendance_rate = fields.Float(string="Attendance Rate", readonly=True)
    final_score = fields.Float(string="Final Score", readonly=True)
    grade = fields.Selection([("A", "A"), ("B", "B"), ("C", "C")], string="Grade", readonly=True)
    pdf_report = fields.Binary(string="PDF Report", attachment=True)
    notes = fields.Text(string="Notes")

    # State
    state = fields.Selection(
        [("draft", "Draft"), ("issued", "Issued"), ("revoked", "Revoked")],
        string="State", default="draft", tracking=True, required=True
    )

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

    # -------- helpers --------
    def _ensure_serial_and_token(self):
        seq = self.env["ir.sequence"]
        for rec in self:
            if not rec.serial_number:
                rec.serial_number = seq.next_by_code("ojt.certificate.seq") or False
            if not rec.qr_token:
                rec.qr_token = uuid.uuid4().hex

    def _fill_scores_from_participant(self):
        """Prefill metrics from participant (participant metrics are computed & stored)."""
        for rec in self:
            p = rec.participant_id
            if not p:
                continue
            # make sure latest values are loaded
            p.flush_recordset(["attendance_rate", "final_score"])
            if not rec.attendance_rate:
                rec.attendance_rate = p.attendance_rate or 0.0
            if not rec.final_score:
                rec.final_score = p.final_score or 0.0
            if not rec.grade:
                fs = rec.final_score or 0.0
                rec.grade = "A" if fs >= 85.0 else ("B" if fs >= 70.0 else "C")

    def _validate_batch_rules(self):
        """Raise ValidationError if participant/certificate doesn't meet batch thresholds."""
        for rec in self:
            b = rec.batch_id or rec.participant_id.batch_id
            if not b:
                continue

            # dukung dua kemungkinan nama field di Batch
            att_req = getattr(b, "certificate_attendance_threshold", None)
            if att_req is None:
                att_req = getattr(b, "attendance_threshold", 0.0) or 0.0

            sc_req = getattr(b, "certificate_score_threshold", None)
            if sc_req is None:
                sc_req = getattr(b, "score_threshold", 0.0) or 0.0

            # nilai aktual di certificate (sudah di-prefill), fallback ke participant
            p = rec.participant_id
            p.flush_recordset(["attendance_rate", "final_score"])
            att_now = rec.attendance_rate or p.attendance_rate or 0.0
            sc_now = rec.final_score or p.final_score or 0.0

            fails = []
            if att_req and att_now < att_req:
                fails.append(_("Attendance %(val).2f%% < required %(req).2f%%") % {"val": att_now, "req": att_req})
            if sc_req and sc_now < sc_req:
                fails.append(_("Final Score %(val).2f < required %(req).2f") % {"val": sc_now, "req": sc_req})

            if fails:
                raise ValidationError(_("Cannot issue certificate:\n- %s") % ("\n- ".join(fails)))

    # -------- actions --------
    def action_issue(self):
        for rec in self:
            rec._fill_scores_from_participant()
            rec._validate_batch_rules()          # <-- gate by batch rules
            rec._ensure_serial_and_token()
            if not rec.issued_on:
                rec.issued_on = fields.Date.context_today(self)
            rec.state = "issued"

    def action_revoke(self):
        self.write({"state": "revoked"})

    def action_reset_draft(self):
        self.write({"state": "draft"})
