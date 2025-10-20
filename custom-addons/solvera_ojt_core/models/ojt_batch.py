# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class OjtBatch(models.Model):
    _name = "ojt.batch"
    _description = "OJT Batch"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "start_date desc, id desc"

    # State: draft -> recruitment -> ongoing -> done/cancel
    state = fields.Selection([
        ("draft", "Draft"),
        ("recruitment", "Recruitment"),
        ("ongoing", "Ongoing"),
        ("done", "Done"),
        ("cancel", "Cancelled"),
    ], string="State", default="draft", tracking=True, required=True)

    # Core identity
    name = fields.Char(string="Batch Name", required=True, tracking=True)
    code = fields.Char(string="Batch Code", readonly=True, copy=False, index=True, default=lambda self: _("New"))

    # Links (HR objects)
    job_id = fields.Many2one("hr.job", string="Recruitment Job", readonly=True, ondelete="restrict")
    department_id = fields.Many2one("hr.department", string="Department")

    # People & relations
    mentor_ids = fields.Many2many(
        "res.partner", "ojt_batch_mentor_rel", "batch_id", "partner_id", string="Mentors"
    )
    participant_ids = fields.One2many("ojt.participant", "batch_id", string="Participants")
    event_link_ids = fields.One2many("ojt.event.link", "batch_id", string="Event Links")
    course_ids = fields.Many2many(
        "slide.channel", "ojt_batch_course_rel", "batch_id", "channel_id", string="Courses"
    )
    assignment_ids = fields.One2many("ojt.assignment", "batch_id", string="Assignments")
    attendance_ids = fields.One2many("ojt.attendance", "batch_id", string="Attendance")

    # Mirrored to hr.job (editable here; sync via inverse)
    capacity = fields.Integer(
        string="Capacity", compute="_compute_capacity", inverse="_inverse_capacity", store=True
    )
    description = fields.Html(
        string="Description", compute="_compute_description", inverse="_inverse_description", store=True
    )

    # Dates & mode
    start_date = fields.Date(string="Start Date", required=True)
    end_date = fields.Date(string="End Date", required=True)
    mode = fields.Selection(
        [("online", "Online"), ("offline", "Offline"), ("hybrid", "Hybrid")],
        string="Mode", default="offline", required=True
    )

    # Rules (certificate thresholds)
    attendance_threshold = fields.Float(string="Certificate Rule (Attendance %)", default=80.0)
    score_threshold = fields.Float(string="Certificate Rule (Score)", default=70.0)

    # Publish (mirror hr.job; controlled by state)
    is_published = fields.Boolean(
        string="Published", compute="_compute_is_published", inverse="_inverse_is_published", store=False
    )

    # Progress (date-based prognosis)
    progress_ratio = fields.Float(
        string="Progress Ratio", compute="_compute_progress_ratio", store=False
    )

    # Smart-button counters
    participants_count = fields.Integer(string="Participants", compute="_compute_counts")
    events_count = fields.Integer(string="Events", compute="_compute_counts")
    assignments_count = fields.Integer(string="Assignments", compute="_compute_counts")
    attendance_count = fields.Integer(string="Attendance", compute="_compute_counts")
    certificates_count = fields.Integer(string="Certificates", compute="_compute_counts")

    _sql_constraints = [
        ("ojt_batch_unique_name", "unique(name)", "Batch name must be unique."),
        ("ojt_batch_unique_job", "unique(job_id)", "Each HR Job can be linked to only one OJT Batch."),
    ]

    # Compute: mirror capacity from hr.job
    @api.depends("job_id")
    def _compute_capacity(self):
        for rec in self:
            rec.capacity = rec.job_id.no_of_recruitment if rec.job_id else 0

    # Inverse: push capacity to hr.job
    def _inverse_capacity(self):
        for rec in self:
            if rec.job_id:
                rec.job_id.with_context(ojt_batch_sync=True).write({"no_of_recruitment": rec.capacity or 0})

    # Compute: mirror description from hr.job
    @api.depends("job_id")
    def _compute_description(self):
        for rec in self:
            rec.description = rec.job_id.description if rec.job_id else False

    # Inverse: push description to hr.job
    def _inverse_description(self):
        for rec in self:
            if rec.job_id:
                rec.job_id.with_context(ojt_batch_sync=True).write({"description": rec.description or False})

    # Helper: resolve publish field on hr.job (new/legacy)
    def _job_publish_field_name(self):
        Job = self.env["hr.job"]
        if "is_published" in Job._fields:
            return "is_published"
        if "website_published" in Job._fields:
            return "website_published"
        return None

    # Compute: mirror publish flag from hr.job
    @api.depends("job_id")
    def _compute_is_published(self):
        fname = self._job_publish_field_name()
        for rec in self:
            rec.is_published = bool(rec.job_id[fname]) if rec.job_id and fname else False

    # Inverse: enforce state rule and push publish flag
    def _inverse_is_published(self):
        fname = self._job_publish_field_name()
        for rec in self:
            if rec.job_id and fname:
                if bool(rec.is_published) and rec.state != "recruitment":
                    raise ValidationError(_("You can publish only when the batch status is Recruitment."))
                rec.job_id.with_context(ojt_batch_sync=True).write({fname: bool(rec.is_published)})

    # Compute: date-based progress %
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

    # Compute: smart-button counters
    def _compute_counts(self):
        Cert = self.env["ojt.certificate"]
        for rec in self:
            rec.participants_count = len(rec.participant_ids)
            rec.events_count = len(rec.event_link_ids)
            rec.assignments_count = len(rec.assignment_ids)
            rec.attendance_count = len(rec.attendance_ids)
            if "batch_id" in Cert._fields:
                rec.certificates_count = Cert.search_count([("batch_id", "=", rec.id)])
            elif "participant_id" in Cert._fields:
                rec.certificates_count = Cert.search_count([("participant_id.batch_id", "=", rec.id)])
            else:
                rec.certificates_count = 0

    # Helper: auto-unpublish when leaving recruitment
    def _auto_unpublish_if_needed(self):
        """Unpublish linked Job when state is not 'recruitment'."""
        fname = self._job_publish_field_name()
        for rec in self:
            if rec.state != "recruitment" and fname and rec.job_id:
                try:
                    if bool(rec.job_id[fname]):
                        rec.job_id.with_context(ojt_batch_sync=True).write({fname: False})
                except Exception:
                    rec.job_id.with_context(ojt_batch_sync=True).write({fname: False})

    # Action: move to recruitment
    def action_set_recruitment(self):
        for rec in self:
            rec.state = "recruitment"

    # Action: start program (ongoing) and unpublish if needed
    def action_set_ongoing(self):
        for rec in self:
            rec.state = "ongoing"
        self._auto_unpublish_if_needed()

    # Action: close program (done) and unpublish if needed
    def action_set_done(self):
        for rec in self:
            rec.state = "done"
        self._auto_unpublish_if_needed()

    # Action: cancel program and unpublish if needed
    def action_set_cancel(self):
        for rec in self:
            rec.state = "cancel"
        self._auto_unpublish_if_needed()

    # Constraint: start_date <= end_date
    @api.constrains("start_date", "end_date")
    def _check_dates(self):
        for rec in self:
            if rec.start_date and rec.end_date and rec.end_date < rec.start_date:
                raise ValidationError(_("End Date cannot be earlier than Start Date."))

    # Constraint: thresholds within 0..100
    @api.constrains("attendance_threshold", "score_threshold")
    def _check_thresholds(self):
        for rec in self:
            for val, label in [
                (rec.attendance_threshold, _("Attendance Threshold")),
                (rec.score_threshold, _("Score Threshold")),
            ]:
                if val is not None and (val < 0.0 or val > 100.0):
                    raise ValidationError(_("%s must be within 0..100.") % label)

    # Create: assign sequence, ensure/create linked hr.job, initial sync
    @api.model_create_multi
    def create(self, vals_list):
        IrSequence = self.env["ir.sequence"]
        HrJob = self.env["hr.job"]
        new_records = self.browse()
        for vals in vals_list:
            if not vals.get("code") or vals.get("code") == _("New"):
                vals["code"] = IrSequence.next_by_code("ojt.batch.seq") or _("New")
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

    # Write: guard publish on state, keep hr.job in sync
    def write(self, vals):
        leaving_ids = set()
        if "state" in vals:
            new_state = vals.get("state")
            for rec in self:
                if new_state != "recruitment":
                    fname = rec._job_publish_field_name()
                    if fname and rec.job_id and bool(rec.job_id[fname]):
                        leaving_ids.add(rec.id)
        res = super().write(vals)
        if leaving_ids:
            for rec in self.browse(list(leaving_ids)):
                fname = rec._job_publish_field_name()
                if fname and rec.job_id:
                    rec.job_id.with_context(ojt_batch_sync=True).write({fname: False})
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

    # Navigation: open participants
    def action_open_participants(self):
        return self._action_open_records("ojt.participant", "Participants", [("batch_id", "=", self.id)])

    # Navigation: open event links
    def action_open_event_links(self):
        return self._action_open_records("ojt.event.link", "Agenda (Events)", [("batch_id", "=", self.id)], view_mode="list,form")

    # Navigation: open assignments
    def action_open_assignments(self):
        return self._action_open_records("ojt.assignment", "Assignments", [("batch_id", "=", self.id)])

    # Navigation: open attendance
    def action_open_attendance(self):
        return self._action_open_records("ojt.attendance", "Attendance", [("batch_id", "=", self.id)])

    # Navigation: open certificates (supports two link schemas)
    def action_open_certificates(self):
        Cert = self.env["ojt.certificate"]
        if "batch_id" in Cert._fields:
            dom = [("batch_id", "=", self.id)]
        else:
            dom = [("participant_id.batch_id", "=", self.id)]
        return self._action_open_records("ojt.certificate", "Certificates", dom)

    # Navigation helper: generic list/form opener
    def _action_open_records(self, model, name, domain, view_mode="list,form"):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": name,
            "res_model": model,
            "view_mode": view_mode,
            "domain": domain,
            "context": {"default_batch_id": self.id, "search_default_batch_id": self.id},
            "target": "current",
        }
