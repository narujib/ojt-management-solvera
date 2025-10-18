# -*- coding: utf-8 -*-
from odoo import api, fields, models

class OjtCertificate(models.Model):
    _name = "ojt.certificate"
    _description = "OJT Certificate (placeholder)"
    _order = "date_issued desc, id desc"

    name = fields.Char(string="Name", required=True, default="Certificate")
    participant_id = fields.Many2one("ojt.participant", string="Participant", required=True, ondelete="cascade", index=True)
    batch_id = fields.Many2one("ojt.batch", string="Batch", related="participant_id.batch_id", store=True, readonly=True)
    date_issued = fields.Date(string="Date Issued")
    notes = fields.Text(string="Notes")
