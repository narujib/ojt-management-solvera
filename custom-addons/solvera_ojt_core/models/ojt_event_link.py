# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class OjtEventLink(models.Model):
    _name = "ojt.event.link"
    _description = "OJT Event Link"
    _order = "date_start, id"
    _rec_name = "title"

    # Identity & links
    batch_id = fields.Many2one("ojt.batch", string="Batch", required=True, ondelete="cascade", index=True)
    event_id = fields.Many2one("event.event", string="Event")
    title = fields.Char(string="Title", related="event_id.name", store=False, readonly=True)

    # Schedule & details
    date_start = fields.Datetime(string="Date Start")
    date_end = fields.Datetime(string="Date End")
    instructor_id = fields.Many2one("res.partner", string="Instructor / Speaker")
    online_meeting_url = fields.Char(string="Online Meeting URL", help="Zoom/Teams/Meet link")
    mandatory = fields.Boolean(string="Mandatory")
    weight = fields.Float(string="Weight")
    notes = fields.Text(string="Notes")

    # Smart-button counters
    participants_count = fields.Integer(string="Participants", compute="_compute_counts")
    attendance_count = fields.Integer(string="Attendance", compute="_compute_counts")
    assignments_count = fields.Integer(string="Assignments", compute="_compute_counts")

    # Compute: counters for participants/attendance/assignments
    @api.depends("batch_id")
    def _compute_counts(self):
        Participant = self.env["ojt.participant"]
        Attendance = self.env["ojt.attendance"]
        Assignment = self.env["ojt.assignment"]
        for rec in self:
            rec.participants_count = Participant.search_count([("batch_id", "=", rec.batch_id.id)]) if rec.batch_id else 0
            rec.attendance_count = Attendance.search_count([("event_link_id", "=", rec.id)]) if rec.id else 0
            rec.assignments_count = Assignment.search_count([("event_link_id", "=", rec.id)]) if rec.id else 0

    # Constraint: date_start <= date_end
    @api.constrains("date_start", "date_end")
    def _check_dates(self):
        for rec in self:
            if rec.date_start and rec.date_end and rec.date_end < rec.date_start:
                raise ValidationError(_("Date End cannot be earlier than Date Start."))

    # Navigation helper: generic opener for related records
    def _action_open_records(self, model, name, domain, view_mode="list,form"):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": name,
            "res_model": model,
            "view_mode": view_mode,
            "domain": domain,
            "context": {
                "default_batch_id": self.batch_id.id,
                "default_event_link_id": self.id,
                "search_default_batch_id": self.batch_id.id,
                "search_default_event_link_id": self.id,
            },
            "target": "current",
        }

    # Navigation: open participants in same batch
    def action_open_participants(self):
        return self._action_open_records("ojt.participant", "Participants", [("batch_id", "=", self.batch_id.id)])

    # Navigation: open attendance for this link
    def action_open_attendance(self):
        return self._action_open_records("ojt.attendance", "Attendance", [("event_link_id", "=", self.id)])

    # Navigation: open assignments for this link
    def action_open_assignments(self):
        return self._action_open_records("ojt.assignment", "Assignments", [("event_link_id", "=", self.id)])
