# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class OjtSubmission(models.Model):
    _name = "ojt.submission"
    _description = "OJT Submission"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "submitted_on desc, id desc"
    _rec_name = "name"

    # Display name: composed from participant and assignment
    name = fields.Char(string="Submission", compute="_compute_name", store=True, index=True)

    # Relations: main links and derived batch
    assignment_id = fields.Many2one(
        "ojt.assignment", string="Assignment", required=True, ondelete="cascade", index=True
    )
    participant_id = fields.Many2one(
        "ojt.participant", string="Participant", required=True, ondelete="cascade", index=True
    )
    assignment_batch_id = fields.Many2one(
        "ojt.batch", string="Assignment Batch", related="assignment_id.batch_id", store=False, readonly=True
    )

    # Core data: timestamp, files, and external URL
    submitted_on = fields.Datetime(string="Submitted On")
    attachment_ids = fields.Many2many(
        "ir.attachment", "ojt_submission_attachment_rel", "submission_id", "attachment_id", string="Attachments"
    )
    submission_url = fields.Char(string="Submission URL", help="External link (GitHub, Figma, video, etc.)")

    # Scoring & review: score, reviewer, and feedback
    score = fields.Float(string="Score", tracking=True)
    reviewer_id = fields.Many2one("res.users", string="Reviewer", default=lambda self: self.env.user)
    feedback = fields.Html(string="Feedback")

    # State: late flag and lifecycle status
    late = fields.Boolean(string="Late", compute="_compute_late", store=True)
    state = fields.Selection(
        [("draft", "Draft"), ("submitted", "Submitted"), ("scored", "Scored")],
        string="State",
        default="draft",
        required=True,
        tracking=True,
    )

    # Compute display name from participant and assignment
    @api.depends("participant_id.display_name", "assignment_id.display_name")
    def _compute_name(self):
        for rec in self:
            p = rec.participant_id.display_name or ""
            a = rec.assignment_id.display_name or ""
            rec.name = f"{p} — {a}" if p and a else (p or a or _("Submission"))

    # Compute 'late' based on submitted_on vs assignment deadline
    @api.depends("submitted_on", "assignment_id", "assignment_id.deadline")
    def _compute_late(self):
        for rec in self:
            if rec.submitted_on and rec.assignment_id and rec.assignment_id.deadline:
                rec.late = rec.submitted_on > rec.assignment_id.deadline
            else:
                rec.late = False

    # Action: move to Submitted and stamp time if missing
    def action_submit(self):
        for rec in self:
            vals = {"state": "submitted"}
            if not rec.submitted_on:
                vals["submitted_on"] = fields.Datetime.now()
            rec.write(vals)
            # Best effort: post a note on related assignment
            try:
                status = _("late") if rec.late else _("on time")
                rec.assignment_id.message_post(
                    body=_("Submission by %s %s at %s") % (rec.participant_id.display_name, status, rec.submitted_on)
                )
            except Exception:
                # Do not fail the transaction if posting fails
                pass

    # Action: finalize scoring
    def action_score(self):
        self.write({"state": "scored"})

    # Smart button: open related assignment
    def action_open_assignment(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "ojt.assignment",
            "view_mode": "form",
            "res_id": self.assignment_id.id,
            "target": "current",
        }

    # Smart button: open related participant
    def action_open_participant(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "ojt.participant",
            "view_mode": "form",
            "res_id": self.participant_id.id,
            "target": "current",
        }

    # Constraint: score must be within 0..max_score
    @api.constrains("score", "assignment_id")
    def _check_score_range(self):
        for rec in self:
            maxs = rec.assignment_id.max_score or 0.0
            if rec.score is not None and (rec.score < 0.0 or rec.score > maxs):
                raise ValidationError(_("Score must be within 0..%(max).2f") % {"max": maxs})

    # Constraint: participant must match the assignment's batch
    @api.constrains("participant_id", "assignment_id")
    def _check_participant_batch(self):
        for rec in self:
            if rec.assignment_id and rec.participant_id and rec.assignment_id.batch_id != rec.participant_id.batch_id:
                raise ValidationError(_("Participant must belong to the same Batch as the Assignment."))
