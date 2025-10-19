
# -*- coding: utf-8 -*-
from odoo import api, fields, models, _

class HrApplicant(models.Model):
    _inherit = "hr.applicant"

    def _is_contract_signed_stage(self, stage):
        """Return True only when the applicant's stage represents 'Contract Signed'."""
        name = (stage.name or "").lower()
        if not name:
            return False
        if "proposal" in name:
            return False
        if ("kontrak" in name and any(k in name for k in ("ditandatangani", "ditandatangan"))) or ("contract" in name and "signed" in name):
            return True
        return False

    # Backward compatibility: route any previous checks here
    def _is_hired_stage(self, stage):
        return self._is_contract_signed_stage(stage)

    def write(self, vals):
        Stage = self.env["hr.recruitment.stage"]
        to_process = []
        if "stage_id" in vals:
            new_stage = Stage.browse(vals["stage_id"])
            for app in self:
                if self._is_contract_signed_stage(new_stage):
                    to_process.append(app.id)

        res = super().write(vals)

        if to_process:
            apps = self.browse(to_process)
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
                    if not exists.applicant_id:
                        exists.write({"applicant_id": app.id})
                    continue
                Participant.create({
                    "batch_id": batch.id,
                    "partner_id": app.partner_id.id,
                    "applicant_id": app.id,
                })
        return res
