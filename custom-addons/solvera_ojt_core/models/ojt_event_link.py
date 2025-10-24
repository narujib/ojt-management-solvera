# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class OjtEventLink(models.Model):
    _name = "ojt.event.link"
    _description = "OJT Event Link"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_start, id"
    _rec_name = "title"

    # Relations: owning batch and source event
    batch_id = fields.Many2one("ojt.batch", string="Batch", required=True, ondelete="cascade", index=True)
    event_id = fields.Many2one("event.event", string="Event")

    # Display: title derived from event
    title = fields.Char(string="Title", related="event_id.name", store=False, readonly=True)

    # Schedule & metadata: timing, instructor, and delivery
    date_start = fields.Datetime(string="Date Start")
    date_end = fields.Datetime(string="Date End")
    instructor_id = fields.Many2one("res.partner", string="Instructor / Speaker")
    online_meeting_url = fields.Char(string="Online Meeting URL", help="Zoom/Teams/Meet link")
    mandatory = fields.Boolean(string="Mandatory")
    weight = fields.Float(string="Weight")
    notes = fields.Text(string="Notes")

    # Counters: participants, attendance, and assignments
    participants_count = fields.Integer(string="Participants", compute="_compute_counts")
    attendance_count = fields.Integer(string="Attendance", compute="_compute_counts")
    assignments_count = fields.Integer(string="Assignments", compute="_compute_counts")

    # Compute: simple counters for related records
    @api.depends("batch_id")
    def _compute_counts(self):
        Participant = self.env["ojt.participant"]
        Attendance = self.env["ojt.attendance"]
        Assignment = self.env["ojt.assignment"]
        for rec in self:
            rec.participants_count = (
                Participant.search_count([("batch_id", "=", rec.batch_id.id)]) if rec.batch_id else 0
            )
            rec.attendance_count = Attendance.search_count([("event_link_id", "=", rec.id)]) if rec.id else 0
            rec.assignments_count = Assignment.search_count([("event_link_id", "=", rec.id)]) if rec.id else 0

    # Constraint: end must not be earlier than start
    @api.constrains("date_start", "date_end")
    def _check_dates(self):
        for rec in self:
            if rec.date_start and rec.date_end and rec.date_end < rec.date_start:
                raise ValidationError(_("Date End cannot be earlier than Date Start."))

    # Action helper: open related records with sane defaults
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

    # Smart buttons: open participants/attendance/assignments
    def action_open_participants(self):
        return self._action_open_records("ojt.participant", "Participants", [("batch_id", "=", self.batch_id.id)])

    def action_open_attendance(self):
        return self._action_open_records("ojt.attendance", "Attendance", [("event_link_id", "=", self.id)])

    def action_open_assignments(self):
        return self._action_open_records("ojt.assignment", "Assignments", [("event_link_id", "=", self.id)])

    def ensure_attendance_for_batch_participants(self):
        Participant = self.env["ojt.participant"].sudo()
        Attendance = self.env["ojt.attendance"].sudo()
        for rec in self:
            if not rec.batch_id:
                continue
            participants = Participant.search([("batch_id", "=", rec.batch_id.id)])
            if not participants:
                continue

            existing = Attendance.read_group(
                domain=[("event_link_id", "=", rec.id)],
                fields=["participant_id"],
                groupby=["participant_id"],
            )
            existing_ids = {e["participant_id"][0] for e in existing if e.get("participant_id")}
            to_create = []
            for p in participants:
                if p.id in existing_ids:
                    continue
                to_create.append({
                    "batch_id": rec.batch_id.id,
                    "event_link_id": rec.id,
                    "participant_id": p.id,
                    "presence": "absent",
                    "method": "manual",
                })
            if to_create:
                Attendance.create(to_create)

            missing = Attendance.search([
                ("event_link_id", "=", rec.id),
                ("qr_token", "=", False),
            ], limit=0)
            for att in missing:
                att.write({"qr_token": uuid4().hex})

    # Override: create and then backfill attendance
    @api.model
    def create(self, vals):
        rec = super().create(vals)
        rec.ensure_attendance_for_batch_participants()
        return rec

    # Override: always re-sync attendance (idempotent)
    def write(self, vals):
        res = super().write(vals)
        if "batch_id" in vals or True:
            self.ensure_attendance_for_batch_participants()
        return res

    # Button: idempotent generator + open attendance
    def action_generate_attendance(self):
        self.ensure_attendance_for_batch_participants()
        self.message_post(body=_("Attendance generated/synced for batch participants."))
        return self.action_open_attendance()
