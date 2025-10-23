# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    # Settings: attendance thresholds and windows
    ojt_late_grace_minutes = fields.Integer(
        string="OJT Late Grace (minutes)",
        default=15,
        config_parameter="ojt_late_grace_minutes",
        help="Max minutes from start to still be counted as Present.",
    )
    ojt_auto_absent_after_minutes = fields.Integer(
        string="OJT Auto Absent After (minutes)",
        default=45,
        config_parameter="ojt_auto_absent_after_minutes",
        help="If not checked in by this threshold, mark as Absent.",
    )
    ojt_auto_checkout_buffer_minutes = fields.Integer(
        string="OJT Auto Checkout Buffer (minutes)",
        default=5,
        config_parameter="ojt_auto_checkout_buffer_minutes",
        help="Auto checkout after event end plus this buffer.",
    )

    # Settings: check-in open/close window
    ojt_early_checkin_open_minutes = fields.Integer(
        string="OJT Early Check-in Open (minutes)",
        default=15,
        config_parameter="ojt_early_checkin_open_minutes",
        help="Minutes before session start when check-in opens.",
    )
    ojt_close_checkin_after_end_minutes = fields.Integer(
        string="OJT Close Check-in After End (minutes)",
        default=0,
        config_parameter="ojt_close_checkin_after_end_minutes",
        help="Minutes after session end when check-in remains open.",
    )
