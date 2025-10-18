# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class OjtEventLink(models.Model):
    _name = "ojt.event.link"
    _description = "OJT Event Link"
    _order = "date_start, id"

    batch_id = fields.Many2one("ojt.batch", string="Batch", required=True, ondelete="cascade", index=True)
    event_id = fields.Many2one("event.event", string="Event")

    title = fields.Char(string="Title", related="event_id.name", store=False, readonly=True)

    date_start = fields.Datetime(string="Date Start")
    date_end = fields.Datetime(string="Date End")

    instructor_id = fields.Many2one("res.partner", string="Instructor / Speaker")
    online_meeting_url = fields.Char(string="Online Meeting URL", help="Zoom/Teams/Meet link")

    mandatory = fields.Boolean(string="Mandatory")
    weight = fields.Float(string="Weight")
    notes = fields.Text(string="Notes")

    @api.constrains("date_start", "date_end")
    def _check_dates(self):
        for rec in self:
            if rec.date_start and rec.date_end and rec.date_end < rec.date_start:
                raise ValidationError(_("Date End cannot be earlier than Date Start."))
