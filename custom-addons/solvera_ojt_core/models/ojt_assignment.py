# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class OjtAssignment(models.Model):
    _name = "ojt.assignment"
    _description = "OJT Assignment"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "deadline, id desc"

    name = fields.Char(string="Assignment Name", required=True, index=True, tracking=True)
    batch_id = fields.Many2one("ojt.batch", string="Batch", required=True, ondelete="cascade", index=True)
    event_link_id = fields.Many2one("ojt.event.link", string="Related Event", ondelete="set null")
    description = fields.Html(string="Description")
    type = fields.Selection([
        ("task","Task"),
        ("quiz","Quiz"),
        ("presentation","Presentation"),
    ], string="Type", default="task", required=True)
    deadline = fields.Datetime(string="Deadline")
    max_score = fields.Float(string="Max Score", default=100.0)
    weight = fields.Float(string="Weight", default=0.0)
    attachment_required = fields.Boolean(string="Attachment Required")
    state = fields.Selection([("draft","Draft"),("open","Open"),("closed","Closed")], string="State", default="draft", required=True, tracking=True)

    submission_ids = fields.One2many("ojt.submission", "assignment_id", string="Submissions")
    submit_count = fields.Integer(string="Submit Count", compute="_compute_submit_count", store=True)

    @api.depends("submission_ids")
    def _compute_submit_count(self):
        for rec in self:
            rec.submit_count = len(rec.submission_ids)

    # State helpers
    def action_open(self):
        self.write({"state": "open"})
    def action_close(self):
        self.write({"state": "closed"})
    def action_reset_draft(self):
        self.write({"state": "draft"})

    @api.constrains("weight")
    def _check_weight(self):
        for rec in self:
            if rec.weight is not None and rec.weight < 0.0:
                raise ValidationError(_("Weight cannot be negative."))

    @api.constrains("event_link_id", "batch_id")
    def _check_event_link_batch(self):
        for rec in self:
            if rec.event_link_id and rec.event_link_id.batch_id != rec.batch_id:
                raise ValidationError(_("Related Event must belong to the same Batch."))

    @api.constrains("max_score")
    def _check_max_score(self):
        for rec in self:
            if rec.max_score is not None and rec.max_score <= 0.0:
                raise ValidationError(_("Max Score must be greater than zero."))

    def action_open_submissions(self):
        self.ensure_one()
        return {
            'name': _('Submissions'),
            'type': 'ir.actions.act_window',
            'res_model': 'ojt.submission',
            'view_mode': 'list,form',
            'domain': [('assignment_id', '=', self.id)],
            'context': {'default_assignment_id': self.id},
        }
