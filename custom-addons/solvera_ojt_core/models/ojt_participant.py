# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class OjtParticipant(models.Model):
    _name = "ojt.participant"
    _description = "OJT Participant"
    _order = "batch_id, partner_id, id desc"

    # Core
    name = fields.Char(
        string="Participant Name",
        compute="_compute_name", store=True, readonly=True, index=True
    )
    batch_id = fields.Many2one(
        "ojt.batch", string="Batch", required=True,
        ondelete="cascade", index=True
    )
    partner_id = fields.Many2one(
        "res.partner", string="Partner", required=True,
        ondelete="restrict", index=True
    )
    applicant_id = fields.Many2one("hr.applicant", string="Applicant", ondelete="set null")

    # Links (needed for compute dependencies)
    submission_ids = fields.One2many(
        "ojt.submission", "participant_id", string="Submissions"
    )
    attendance_ids = fields.One2many(
        "ojt.attendance", "participant_id", string="Attendance"
    )

    # KPIs (computed & stored)
    attendance_rate = fields.Float(
        string="Attendance Rate (%)",
        compute="_compute_metrics", store=True, readonly=True
    )
    average_score = fields.Float(
        string="Average Score",
        compute="_compute_metrics", store=True, readonly=True
    )
    final_score = fields.Float(
        string="Final Score",
        compute="_compute_metrics", store=True, readonly=True
    )
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
        ("unique_batch_partner", "unique(batch_id, partner_id)", "Participant must be unique per Batch."),
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

    @api.depends(
        "batch_id",
        "attendance_ids.presence",
        "submission_ids.score",
        "submission_ids.assignment_id.max_score",
        "submission_ids.assignment_id.weight",
        "submission_ids.assignment_id.batch_id",
        "mentor_score",
    )
    def _compute_metrics(self):
        for rec in self:
            # ---- Attendance Rate ----
            total = len(rec.attendance_ids)
            present = sum(1 for a in rec.attendance_ids if a.presence in ("present", "late"))
            rec.attendance_rate = (present / total * 100.0) if total else 0.0

            # ---- Scores from submissions (best per assignment, weighted) ----
            subs = rec.submission_ids.filtered(
                lambda s: s.assignment_id and s.assignment_id.batch_id == rec.batch_id
            )

            if not subs:
                task_avg = 0.0
                task_final = 0.0
            else:
                by_assign = {}
                for s in subs:
                    asg = s.assignment_id
                    if not asg or (asg.max_score or 0.0) <= 0:
                        continue
                    cur_best = by_assign.get(asg.id)
                    if cur_best is None or (s.score or 0.0) > (cur_best.score or 0.0):
                        by_assign[asg.id] = s

                normals = []
                w_sum = 0.0
                w_tot = 0.0
                for s in by_assign.values():
                    maxs = s.assignment_id.max_score or 0.0
                    if maxs <= 0:
                        continue
                    norm = (s.score or 0.0) / maxs * 100.0
                    normals.append(norm)
                    w = s.assignment_id.weight or 0.0
                    w_sum += norm * w
                    w_tot += w

                task_avg = sum(normals) / len(normals) if normals else 0.0
                task_final = (w_sum / w_tot) if w_tot else task_avg

            # Simpan average dari tugas (tanpa mentor)
            rec.average_score = task_avg

            # ---- Combine dengan Mentor ----
            TASK_W = 0.80
            MENTOR_W = 0.20
            mentor = rec.mentor_score or 0.0

            rec.final_score = round((task_final * TASK_W) + (mentor * MENTOR_W), 2)

    # Quick state helpers
    def action_set_active(self): self.write({"state": "active"})
    def action_set_completed(self): self.write({"state": "completed"})
    def action_set_failed(self): self.write({"state": "failed"})
    def action_set_left(self): self.write({"state": "left"})
    def action_set_draft(self): self.write({"state": "draft"})
