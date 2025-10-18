# -*- coding: utf-8 -*-
from odoo import models, fields

class OjtParticipant(models.Model):
    _name = "ojt.participant"
    _description = "OJT Participant (placeholder for Step 2.x)"
    _order = "id desc"

    name = fields.Char(string="Name", required=True)
    partner_id = fields.Many2one("res.partner", string="Contact")
    batch_id = fields.Many2one("ojt.batch", string="Batch", required=True, ondelete="cascade")
