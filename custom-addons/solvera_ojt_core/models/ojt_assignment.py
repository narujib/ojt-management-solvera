# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class OjtAssignment(models.Model):
    _name = "ojt.assignment"
    _description = "OJT Assignment"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "deadline, id desc"

    # State: draft → open → closed
    state = fields.Selection([
        ("draft", "Draft"),
        ("open", "Open"),
        ("closed", "Closed"),
    ], string="State", default="draft", required=True, tracking=True)

    # Identity & links
    name = fields.Char(string="Assignment Name", required=True, index=True, tracking=True)
    batch_id = fields.Many2one("ojt.batch", string="Batch", required=True, ondelete="cascade", index=True)
    event_link_id = fields.Many2one("ojt.event.link", string="Related Event", ondelete="set null")
    description = fields.Html(string="Description")
    type = fields.Selection([
        ("task", "Task"),
        ("quiz", "Quiz"),
        ("presentation", "Presentation"),
    ], string="Type", default="task", required=True)
    deadline = fields.Datetime(string="Deadline")
    max_score = fields.Float(string="Max Score", default=100.0)
    weight = fields.Float(string="Weight", default=0.0)
    attachment_required = fields.Boolean(string="Attachment Required")

    # Children: related rows
    submission_ids = fields.One2many("ojt.submission", "assignment_id", string="Submissions")

    # KPIs: aggregates
    submit_count = fields.Integer(string="Submit Count", compute="_compute_submit_count", store=True)
    participant_count = fields.Integer(string="Participants", compute="_compute_participant_count")
    avg_score = fields.Float(
        string="Avg. Score (%)",
        compute="_compute_avg_score",
        store=True,
        help="Average score normalized to 0..100."
    )
    submission_progress = fields.Float(
        string="Submission Progress (%)",
        compute="_compute_submission_progress",
        help="Participants submitted / total (%)."
    )

    # Compute: submission counter
    @api.depends("submission_ids")
    def _compute_submit_count(self):
        for rec in self:
            rec.submit_count = len(rec.submission_ids)

    # Compute: participant counter
    @api.depends("batch_id")
    def _compute_participant_count(self):
        Part = self.env["ojt.participant"]
        for rec in self:
            rec.participant_count = Part.search_count([("batch_id", "=", rec.batch_id.id)]) if rec.batch_id else 0

    # Compute: average score (normalized)
    @api.depends("submission_ids.score", "max_score")
    def _compute_avg_score(self):
        for rec in self:
            scores = [s.score for s in rec.submission_ids if s.score is not None]
            if not scores:
                rec.avg_score = 0.0
                continue
            if (rec.max_score or 0.0) > 0:
                normalized = [min(max(sc, 0.0), rec.max_score) / rec.max_score * 100.0 for sc in scores]
                avg = sum(normalized) / len(normalized)
            else:
                avg = min(max(sum(scores) / len(scores), 0.0), 100.0)
            rec.avg_score = round(avg, 2)

    # Compute: submission progress
    @api.depends("submission_ids", "batch_id")
    def _compute_submission_progress(self):
        Part = self.env["ojt.participant"]
        for rec in self:
            part_cnt = Part.search_count([("batch_id", "=", rec.batch_id.id)]) if rec.batch_id else 0
            sub_cnt = len(rec.submission_ids)
            rec.submission_progress = round((sub_cnt / part_cnt * 100.0), 0) if part_cnt else 0.0

    # Transition: to open
    def action_open(self):
        self.write({"state": "open"})

    # Transition: to closed
    def action_close(self):
        self.write({"state": "closed"})

    # Transition: reset to draft
    def action_reset_draft(self):
        self.write({"state": "draft"})

    # Constraint: weight >= 0
    @api.constrains("weight")
    def _check_weight(self):
        for rec in self:
            if rec.weight is not None and rec.weight < 0.0:
                raise ValidationError(_("Weight cannot be negative."))

    # Constraint: event link must match batch
    @api.constrains("event_link_id", "batch_id")
    def _check_event_link_batch(self):
        for rec in self:
            if rec.event_link_id and rec.event_link_id.batch_id != rec.batch_id:
                raise ValidationError(_("Related Event must belong to the same Batch."))

    # Constraint: max_score > 0
    @api.constrains("max_score")
    def _check_max_score(self):
        for rec in self:
            if rec.max_score is not None and rec.max_score <= 0.0:
                raise ValidationError(_("Max Score must be greater than zero."))

    # Action: open submissions
    def action_open_submissions(self):
        self.ensure_one()
        return {
            "name": _("Submissions"),
            "type": "ir.actions.act_window",
            "res_model": "ojt.submission",
            "view_mode": "list,form",
            "domain": [("assignment_id", "=", self.id)],
            "context": {
                "default_assignment_id": self.id,
                "default_batch_id": self.batch_id.id,
            },
        }

    # Action: open participants
    def action_open_participants(self):
        self.ensure_one()
        return {
            "name": _("Participants"),
            "type": "ir.actions.act_window",
            "res_model": "ojt.participant",
            "view_mode": "list,form",
            "domain": [("batch_id", "=", self.batch_id.id)],
            "context": {
                "default_batch_id": self.batch_id.id,
            },
        }

    # Action: score overview (graph/pivot/list)
    def action_open_score_overview(self):
        self.ensure_one()
        return {
            "name": _("Score Overview"),
            "type": "ir.actions.act_window",
            "res_model": "ojt.submission",
            "view_mode": "graph,pivot,list",
            "domain": [("assignment_id", "=", self.id)],
            "context": {
                "default_assignment_id": self.id,
                "graph_measure": "score",
                "pivot_measures": ["score"],
                "group_by": ["participant_id"],
            },
        }
