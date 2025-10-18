# -*- coding: utf-8 -*-
from odoo import models, fields

class OjtEventLink(models.Model):
    _name = "ojt.event.link"
    _description = "OJT Event Link (placeholder for Step 2.x)"
    _order = "sequence, id"

    name = fields.Char(string="Title", required=True)
    sequence = fields.Integer(default=10)
    batch_id = fields.Many2one("ojt.batch", string="Batch", required=True, ondelete="cascade")
    date_start = fields.Datetime(string="Start")
    date_end = fields.Datetime(string="End")
    notes = fields.Html(string="Notes")
