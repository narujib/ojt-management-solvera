# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class HrApplicant(models.Model):
    _inherit = "hr.applicant"

    def _notify_stage_change(self, old_stage, new_stage):
        """Send notification email to the applicant when the stage changes.
        If the mail template is missing, post a simple message instead.
        """
        template = self.env.ref("solvera_ojt_core.mail_tmpl_applicant_stage_default", raise_if_not_found=False)
        for app in self:
            partner = getattr(app, "partner_id", False)
            if not partner or not partner.email:
                continue
            if template:
                lang = partner.lang or self.env.user.lang
                template.with_context(lang=lang).send_mail(
                    app.id, force_send=True,
                    email_values={"email_to": partner.email}
                )
            else:
                app.message_post(
                    body=_("Your application moved to stage: %s") % (new_stage.name or ""),
                    message_type="comment",
                    partner_ids=[partner.id],
                    subtype_xmlid="mail.mt_comment",
                    email_layout_xmlid="mail.mail_notification_light"
                )

    def _is_contract_signed_stage(self, stage):
        """Return True only if the stage name clearly indicates 'Contract Signed'.
        Excludes 'Proposal Contract' stages.
        """
        name = (stage.name or "").lower()
        if not name:
            return False
        # Skip 'Proposal Contract' stages
        if "proposal" in name:
            return False
        # Match: 'Kontrak Ditandatangani' / 'Contract Signed'
        return (
            ("kontrak" in name and any(k in name for k in ("ditandatangani", "ditandatangan")))
            or ("contract" in name and "signed" in name)
        )

    def _is_hired_stage(self, stage):
        """Backward compatibility alias for 'contract signed' stage check."""
        return self._is_contract_signed_stage(stage)

    def write(self, vals):
        """Override write() to:
        - Detect stage changes and send notifications
        - Auto-create Participant record if contract is signed
        """
        Stage = self.env["hr.recruitment.stage"]
        stage_changed_ids = []
        to_create_participant_ids = []
        old_stages = {rec.id: rec.stage_id for rec in self}  # Keep old stage for comparison

        # Detect stage change and prepare participant creation
        if "stage_id" in vals:
            new_stage = Stage.browse(vals["stage_id"])
            for app in self:
                stage_changed_ids.append(app.id)
                if self._is_contract_signed_stage(new_stage):
                    to_create_participant_ids.append(app.id)

        # Perform standard write
        res = super().write(vals)

        # Send email notifications for stage changes
        if stage_changed_ids:
            apps = self.browse(stage_changed_ids)
            for app in apps:
                self._notify_stage_change(old_stages.get(app.id), app.stage_id)

        # Auto-create Participant when contract is signed
        if to_create_participant_ids:
            apps = self.browse(to_create_participant_ids)
            Batch = self.env["ojt.batch"]
            Participant = self.env["ojt.participant"]
            for app in apps:
                if not app.job_id or not app.partner_id:
                    continue
                # Find batch linked to this job (1-1 mapping job <-> batch)
                batch = Batch.search([("job_id", "=", app.job_id.id)], limit=1)
                if not batch:
                    continue
                # Avoid duplicates (unique per batch + partner)
                exists = Participant.search([
                    ("batch_id", "=", batch.id),
                    ("partner_id", "=", app.partner_id.id)
                ], limit=1)
                if exists:
                    # Update applicant link if missing
                    if not exists.applicant_id:
                        exists.write({"applicant_id": app.id})
                    continue
                # Create new participant record
                Participant.create({
                    "batch_id": batch.id,
                    "partner_id": app.partner_id.id,
                    "applicant_id": app.id,
                })
        return res
