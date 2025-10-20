# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from urllib.parse import quote  # URL-safe return path


class OjtParticipant(models.Model):
    _name = "ojt.participant"
    _description = "OJT Participant"
    _order = "batch_id, partner_id, id desc"

    # State: draft -> active -> completed/failed/left
    state = fields.Selection([
        ("draft", "Draft"),
        ("active", "Active"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("left", "Left"),
    ], string="State", default="draft", required=True, tracking=True)

    # Identity & links
    name = fields.Char(string="Participant Name", compute="_compute_name", store=True, readonly=True, index=True)
    batch_id = fields.Many2one("ojt.batch", string="Batch", required=True, ondelete="cascade", index=True)
    partner_id = fields.Many2one("res.partner", string="Partner", required=True, ondelete="restrict", index=True)
    applicant_id = fields.Many2one("hr.applicant", string="Applicant", ondelete="set null")
    batch_job_id = fields.Many2one("hr.job", string="Batch Job", related="batch_id.job_id", store=True, readonly=True)

    # Related records
    submission_ids = fields.One2many("ojt.submission", "participant_id", string="Submissions")
    attendance_ids = fields.One2many("ojt.attendance", "participant_id", string="Attendance")
    certificate_ids = fields.One2many("ojt.certificate", "participant_id", string="Certificates")

    # KPIs (computed & stored)
    attendance_rate = fields.Float(string="Attendance Rate (%)", compute="_compute_metrics", store=True, readonly=True)
    average_score = fields.Float(string="Average Score", compute="_compute_metrics", store=True, readonly=True)
    final_score = fields.Float(string="Final Score", compute="_compute_metrics", store=True, readonly=True)
    mentor_score = fields.Float(string="Mentor Score", default=0.0)

    # Smart-button counters
    submission_count = fields.Integer(string="Submissions", compute="_compute_counts")
    attendance_count = fields.Integer(string="Attendance", compute="_compute_counts")
    certificate_count = fields.Integer(string="Certificates", compute="_compute_counts")

    # Notes & portal
    notes = fields.Text(string="Notes")
    portal_token = fields.Char(string="Portal Token")

    _sql_constraints = [
        ("unique_batch_partner", "unique(batch_id, partner_id)", "Participant must be unique per Batch."),
    ]

    # Compute: human-readable name "Partner — Batch"
    @api.depends("partner_id", "batch_id")
    def _compute_name(self):
        for rec in self:
            pname = rec.partner_id.name or ""
            bname = rec.batch_id.name or ""
            sep = " — " if pname and bname else ""
            rec.name = f"{pname}{sep}{bname}"

    # Constraints: KPI ranges and applicant-partner consistency
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

    @api.constrains("applicant_id", "partner_id")
    def _check_applicant_partner(self):
        for rec in self:
            if rec.applicant_id and rec.partner_id and getattr(rec.applicant_id, "partner_id", False):
                if rec.applicant_id.partner_id.id != rec.partner_id.id:
                    raise ValidationError(_("Applicant's partner must match the Participant's partner."))

    # Compute: attendance rate and (weighted) scores
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
            total = len(rec.attendance_ids)
            present = sum(1 for a in rec.attendance_ids if a.presence in ("present", "late"))
            rec.attendance_rate = (present / total * 100.0) if total else 0.0

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

            rec.average_score = task_avg
            TASK_W = 0.80
            MENTOR_W = 0.20
            mentor = rec.mentor_score or 0.0
            rec.final_score = round((task_final * TASK_W) + (mentor * MENTOR_W), 2)

    # State transitions
    def action_set_active(self): self.write({"state": "active"})
    def action_set_completed(self): self.write({"state": "completed"})
    def action_set_failed(self): self.write({"state": "failed"})
    def action_set_left(self): self.write({"state": "left"})
    def action_set_draft(self): self.write({"state": "draft"})

    # Compute: smart-button totals
    def _compute_counts(self):
        Sub = self.env["ojt.submission"]
        Att = self.env["ojt.attendance"]
        Cert = self.env["ojt.certificate"]
        for rec in self:
            rec.submission_count = Sub.search_count([("participant_id", "=", rec.id)])
            rec.attendance_count = Att.search_count([("participant_id", "=", rec.id)])
            rec.certificate_count = Cert.search_count([("participant_id", "=", rec.id)])

    # Navigation: open submissions filtered by participant
    def action_open_assignments(self):
        """Open participant's task list (via submissions)."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Assignments"),
            "res_model": "ojt.submission",
            "view_mode": "list,form",
            "domain": [("participant_id", "=", self.id)],
            "context": {
                "default_participant_id": self.id,
                "search_default_participant_id": self.id,
                "default_batch_id": self.batch_id.id,
            },
        }

    # Navigation: open attendance filtered by participant
    def action_open_attendance(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Attendance"),
            "res_model": "ojt.attendance",
            "view_mode": "list,form",
            "domain": [("participant_id", "=", self.id)],
            "context": {
                "default_participant_id": self.id,
                "default_batch_id": self.batch_id.id,
                "search_default_participant_id": self.id,
            },
        }

    # Navigation: open certificates filtered by participant
    def action_open_certificates(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Certificates"),
            "res_model": "ojt.certificate",
            "view_mode": "list,form",
            "domain": [("participant_id", "=", self.id)],
            "context": {
                "default_participant_id": self.id,
                "default_batch_id": self.batch_id.id,
                "search_default_participant_id": self.id,
            },
        }

    # Navigation: open portal page with backend return URL
    def action_open_portal(self):
        """Open participant portal in a new tab; include return URL to this form."""
        self.ensure_one()
        ret = f"/web#id={self.id}&model=ojt.participant&view_type=form"
        url = f"/my/ojt/participant/{self.id}?ret={quote(ret, safe='')}"
        return {
            "type": "ir.actions.act_url",
            "name": _("Open in Portal"),
            "url": url,
            "target": "new",
        }
