# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class OjtSubmission(models.Model):
    _name = "ojt.submission"
    _description = "OJT Submission"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "submitted_on desc, id desc"

    assignment_id = fields.Many2one("ojt.assignment", string="Assignment", required=True, ondelete="cascade", index=True)
    participant_id = fields.Many2one("ojt.participant", string="Participant", required=True, ondelete="cascade", index=True)
    assignment_batch_id = fields.Many2one("ojt.batch", string="Assignment Batch", related="assignment_id.batch_id", store=False, readonly=True)
    submitted_on = fields.Datetime(string="Submitted On")

    attachment_ids = fields.Many2many("ir.attachment", "ojt_submission_attachment_rel", "submission_id", "attachment_id", string="Attachments")
    submission_url = fields.Char(string="Submission URL", help="External link (GitHub, Figma, video, etc.)")

    score = fields.Float(string="Score")
    reviewer_id = fields.Many2one("res.users", string="Reviewer", default=lambda self: self.env.user)
    feedback = fields.Html(string="Feedback")

    late = fields.Boolean(string="Late", compute="_compute_late", store=True)
    state = fields.Selection([("draft","Draft"),("submitted","Submitted"),("scored","Scored")], string="State", default="draft", required=True, tracking=True)

    @api.depends("submitted_on", "assignment_id", "assignment_id.deadline")
    def _compute_late(self):
        for rec in self:
            if rec.submitted_on and rec.assignment_id and rec.assignment_id.deadline:
                rec.late = rec.submitted_on > rec.assignment_id.deadline
            else:
                rec.late = False

    # Actions
    def action_submit(self):
        for rec in self:
            vals = {"state": "submitted"}
            if not rec.submitted_on:
                vals["submitted_on"] = fields.Datetime.now()
            rec.write(vals)
            # Post chatter on assignment with late/on-time info
            status = _("late") if rec.late else _("on time")
            try:
                rec.assignment_id.message_post(body=_("Submission by %s %s at %s") % (rec.participant_id.display_name, status, rec.submitted_on))
            except Exception:
                pass

    def action_score(self):
        self.write({"state": "scored"})

    # Constraints
    @api.constrains("score", "assignment_id")
    def _check_score_range(self):
        for rec in self:
            maxs = rec.assignment_id.max_score or 0.0
            if rec.score is not None and (rec.score < 0.0 or rec.score > maxs):
                raise ValidationError(_("Score must be within 0..%(max).2f") % {'max': maxs})

    @api.constrains("participant_id", "assignment_id")
    def _check_participant_batch(self):
        for rec in self:
            if rec.assignment_id and rec.participant_id and rec.assignment_id.batch_id != rec.participant_id.batch_id:
                raise ValidationError(_("Participant must belong to the same Batch as the Assignment."))
