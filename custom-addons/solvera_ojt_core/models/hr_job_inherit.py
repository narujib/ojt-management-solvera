from odoo import models, _
from odoo.exceptions import ValidationError

class HrJob(models.Model):
    _inherit = "hr.job"

    def write(self, vals):
        # Guard: block direct edits for batch-controlled fields
        protected = {"name", "description", "no_of_recruitment"}
        if any(k in vals for k in protected) and not self.env.context.get("ojt_batch_sync"):
            linked = self.env["ojt.batch"].sudo().search([("job_id", "in", self.ids)], limit=1)
            if linked:
                raise ValidationError(_("Please edit Job Name/Description/Target via the related OJT Batch only."))

        # Guard: publishing allowed only when linked batch is 'ongoing' (unless triggered from batch sync)
        publish_keys = [k for k in ("is_published", "website_published") if k in vals]
        if publish_keys and not self.env.context.get("ojt_batch_sync"):
            new_val = bool(vals[publish_keys[0]])
            if new_val:  # trying to set True
                # If any linked batch not ongoing -> block
                linked_batches = self.env["ojt.batch"].sudo().search([("job_id", "in", self.ids)])
                for b in linked_batches:
                    if b.state != "recruitment":
                        raise ValidationError(_("You can publish only when the related OJT Batch is Ongoing."))

        return super().write(vals)
