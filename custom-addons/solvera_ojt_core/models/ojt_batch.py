# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class OjtBatch(models.Model):
    _name = "ojt.batch"
    _description = "OJT Batch"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "start_date desc, id desc"

    # Core identity
    name = fields.Char(string="Batch Name", required=True, tracking=True)
    code = fields.Char(string="Batch Code", readonly=True, copy=False, index=True, default=lambda self: _("New"))

    # Links
    job_id = fields.Many2one("hr.job", string="Recruitment Job", readonly=True, ondelete="restrict")
    department_id = fields.Many2one("hr.department", string="Department")

    # Additional fields
    mentor_ids = fields.Many2many(
        "res.partner", "ojt_batch_mentor_rel", "batch_id", "partner_id",
        string="Mentors", help="List of mentors for this batch."
    )
    participant_ids = fields.One2many("ojt.participant", "batch_id", string="Participants")
    event_link_ids = fields.One2many("ojt.event.link", "batch_id", string="Event Links")
    course_ids = fields.Many2many(
        "slide.channel", "ojt_batch_course_rel", "batch_id", "channel_id",
        string="Courses"
    )

    # Mirrored to hr.job
    capacity = fields.Integer(
        string="Capacity",
        compute="_compute_capacity",
        inverse="_inverse_capacity",
        store=True,
        help="Mirrors HR Job target recruitment. Edited here only."
    )
    description = fields.Html(
        string="Description",
        compute="_compute_description",
        inverse="_inverse_description",
        store=True,
        help="Mirrors HR Job description. Edited here only."
    )

    # Dates & mode
    start_date = fields.Date(string="Start Date", required=True)
    end_date = fields.Date(string="End Date", required=True)
    mode = fields.Selection(
        [("online", "Online"), ("offline", "Offline"), ("hybrid", "Hybrid")],
        string="Mode", default="offline", required=True
    )

    # Rules
    attendance_threshold = fields.Float(string="Certificate Rule (Attendance %)", default=80.0)
    score_threshold = fields.Float(string="Certificate Rule (Score)", default=70.0)

    # Publish (mirrors hr.job publish state)
    is_published = fields.Boolean(
        string="Published",
        compute="_compute_is_published",
        inverse="_inverse_is_published",
        store=False,
        help="Publish state of the related HR Job (website)."
    )

    # Progress (informational)
    progress_ratio = fields.Float(
        string="Progress Ratio",
        compute="_compute_progress_ratio",
        store=False,
        help="Auto-calculated based on date window (%)."
    )

    state = fields.Selection(
        [("draft", "Draft"), ("recruitment", "Recruitment"), ("ongoing", "Ongoing"), ("done", "Done"), ("cancel", "Cancelled")],
        string="State", default="draft", tracking=True, required=True
    )

    _sql_constraints = [
        ("ojt_batch_unique_name", "unique(name)", "Batch name must be unique."),
        ("ojt_batch_unique_job", "unique(job_id)", "Each HR Job can be linked to only one OJT Batch."),
    ]

    # ----------- Compute / Inverse -----------
    @api.depends("job_id")
    def _compute_capacity(self):
        for rec in self:
            rec.capacity = rec.job_id.no_of_recruitment if rec.job_id else 0

    def _inverse_capacity(self):
        for rec in self:
            if rec.job_id:
                rec.job_id.with_context(ojt_batch_sync=True).write({"no_of_recruitment": rec.capacity or 0})

    @api.depends("job_id")
    def _compute_description(self):
        for rec in self:
            rec.description = rec.job_id.description if rec.job_id else False

    def _inverse_description(self):
        for rec in self:
            if rec.job_id:
                rec.job_id.with_context(ojt_batch_sync=True).write({"description": rec.description or False})

    def _job_publish_field_name(self):
        Job = self.env["hr.job"]
        if "is_published" in Job._fields:
            return "is_published"
        if "website_published" in Job._fields:
            return "website_published"
        return None

    @api.depends("job_id")
    def _compute_is_published(self):
        fname = self._job_publish_field_name()
        for rec in self:
            rec.is_published = bool(rec.job_id[fname]) if rec.job_id and fname else False

    def _inverse_is_published(self):
        fname = self._job_publish_field_name()
        for rec in self:
            if rec.job_id and fname:
                # Only allow publish=True when ongoing (unpublish allowed anytime via server)
                if bool(rec.is_published) and rec.state != "recruitment":
                    raise ValidationError(_("You can publish only when the batch status is Ongoing."))
                rec.job_id.with_context(ojt_batch_sync=True).write({fname: bool(rec.is_published)})

    @api.depends("start_date", "end_date")
    def _compute_progress_ratio(self):
        today = fields.Date.context_today(self)
        for rec in self:
            if not rec.start_date or not rec.end_date or rec.end_date < rec.start_date:
                rec.progress_ratio = 0.0
                continue
            total = (rec.end_date - rec.start_date).days or 1
            elapsed = (min(today, rec.end_date) - rec.start_date).days
            rec.progress_ratio = max(0.0, min(100.0, (elapsed / total) * 100.0))

    def _auto_unpublish_if_needed(self):
        """Unpublish the linked HR Job when batch state is not 'recruitment'."""
        fname = self._job_publish_field_name()
        for rec in self:
            if rec.state != "recruitment" and fname and rec.job_id:
                try:
                    if bool(rec.job_id[fname]):
                        rec.job_id.with_context(ojt_batch_sync=True).write({fname: False})
                except Exception:
                    rec.job_id.with_context(ojt_batch_sync=True).write({fname: False})

    def action_set_recruitment(self):
        for rec in self:
            rec.state = "recruitment"

    def action_set_ongoing(self):
        for rec in self:
            rec.state = "ongoing"
        self._auto_unpublish_if_needed()

    def action_set_done(self):
        for rec in self:
            rec.state = "done"
        self._auto_unpublish_if_needed()

    def action_set_cancel(self):
        for rec in self:
            rec.state = "cancel"
        self._auto_unpublish_if_needed()

    # ----------- Constraints & sequence -----------
    @api.constrains("start_date", "end_date")
    def _check_dates(self):
        for rec in self:
            if rec.start_date and rec.end_date and rec.end_date < rec.start_date:
                raise ValidationError(_("End Date cannot be earlier than Start Date."))

    @api.constrains("attendance_threshold", "score_threshold")
    def _check_thresholds(self):
        for rec in self:
            for val, label in [
                (rec.attendance_threshold, _("Attendance Threshold")),
                (rec.score_threshold, _("Score Threshold")),
            ]:
                if val is not None and (val < 0.0 or val > 100.0):
                    raise ValidationError(_("%s must be within 0..100.") % label)

    @api.model_create_multi
    def create(self, vals_list):
        IrSequence = self.env["ir.sequence"]
        HrJob = self.env["hr.job"]
        new_records = self.browse()
        for vals in vals_list:
            # Sequence
            if not vals.get("code") or vals.get("code") == _("New"):
                vals["code"] = IrSequence.next_by_code("ojt.batch.seq") or _("New")
            # Ensure HR Job
            job_id = vals.get("job_id")
            name = vals.get("name")
            if not job_id:
                if not name:
                    raise ValidationError(_("Batch Name is required to create a linked Job."))
                jvals = {"name": name}
                if "description" in vals:
                    jvals["description"] = vals.get("description")
                if "capacity" in vals:
                    jvals["no_of_recruitment"] = vals.get("capacity") or 0
                job = HrJob.sudo().create(jvals)
                vals["job_id"] = job.id
            else:
                if name:
                    self.env["hr.job"].browse(job_id).with_context(ojt_batch_sync=True).write({"name": name})
            new_records |= super(OjtBatch, self).create([vals])
        return new_records

    def write(self, vals):
        # Track which records are published and will leave 'recruitment'
        leaving_ids = set()
        if 'state' in vals:
            new_state = vals.get('state')
            for rec in self:
                if new_state != 'recruitment':
                    # Check current publish status from HR Job
                    fname = rec._job_publish_field_name()
                    if fname and rec.job_id and bool(rec.job_id[fname]):
                        leaving_ids.add(rec.id)

        res = super().write(vals)

        # After write, unpublish those that left recruitment
        if leaving_ids:
            for rec in self.browse(list(leaving_ids)):
                fname = rec._job_publish_field_name()
                if fname and rec.job_id:
                    rec.job_id.with_context(ojt_batch_sync=True).write({fname: False})

        # Existing syncs
        for rec in self:
            if "name" in vals and rec.job_id:
                rec.job_id.with_context(ojt_batch_sync=True).write({"name": rec.name})
            if "capacity" in vals:
                rec._inverse_capacity()
            if "description" in vals:
                rec._inverse_description()
            if "is_published" in vals:
                rec._inverse_is_published()

        return res