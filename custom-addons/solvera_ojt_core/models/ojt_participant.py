# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class OjtParticipant(models.Model):
    _name = "ojt.participant"
    _description = "OJT Participant"
    _order = "batch_id, partner_id, id desc"

    # Core
    name = fields.Char(string="Participant Name", compute="_compute_name", store=True, readonly=True, index=True)
    batch_id = fields.Many2one("ojt.batch", string="Batch", required=True, ondelete="cascade", index=True)
    partner_id = fields.Many2one("res.partner", string="Partner", required=True, ondelete="restrict", index=True)
    applicant_id = fields.Many2one("hr.applicant", string="Applicant", ondelete="set null")

    # KPIs
    attendance_rate = fields.Float(string="Attendance Rate (%)", default=0.0)
    average_score = fields.Float(string="Average Score", default=0.0)
    final_score = fields.Float(string="Final Score", default=0.0)
    mentor_score = fields.Float(string="Mentor Score", default=0.0)

    state = fields.Selection([
        ("draft", "Draft"),
        ("active", "Active"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("left", "Left"),
    ], string="State", default="draft", required=True, tracking=True)

    certificate_ids = fields.One2many("ojt.certificate", "participant_id", string="Certificates")
    notes = fields.Text(string="Notes")
    portal_token = fields.Char(string="Portal Token")

    _sql_constraints = [
        ("unique_batch_partner", "unique(batch_id, partner_id)", "Participant must be unique per Batch.")
    ]

    @api.depends("partner_id", "batch_id")
    def _compute_name(self):
        for rec in self:
            pname = rec.partner_id.name or ""
            bname = rec.batch_id.name or ""
            sep = " — " if pname and bname else ""
            rec.name = f"{pname}{sep}{bname}"

    @api.constrains("attendance_rate", "average_score", "final_score", "mentor_score")
    def _check_scores(self):
        for rec in self:
            for val, label in [
                (rec.attendance_rate, _("Attendance Rate")),
                (rec.average_score, _("Average Score")),
                (rec.final_score, _("Final Score")),
                (rec.mentor_score, _("Mentor Score")),
            ]:
                if val is not None and (val < 0.0 or val > 100.0):
                    raise ValidationError(_("%s must be within 0..100.") % label)

    # Simple state actions (optional but handy)
    def action_set_active(self):
        self.write({"state": "active"})
    def action_set_completed(self):
        self.write({"state": "completed"})
    def action_set_failed(self):
        self.write({"state": "failed"})
    def action_set_left(self):
        self.write({"state": "left"})
    def action_set_draft(self):
        self.write({"state": "draft"})
