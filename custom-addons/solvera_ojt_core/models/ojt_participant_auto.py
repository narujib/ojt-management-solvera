# -*- coding: utf-8 -*-
from odoo import api, models


class OjtParticipant(models.Model):
    _inherit = "ojt.participant"

    # Hook: ensure attendance rows after create
    @api.model
    def create(self, vals):
        rec = super().create(vals)
        rec._ensure_attendance_for_existing_events()
        return rec

    # Hook: re-sync attendance when batch changes
    def write(self, vals):
        res = super().write(vals)
        if "batch_id" in vals:
            self._ensure_attendance_for_existing_events()
        return res

    # Helper: create attendance rows for all events in the participant's batch
    def _ensure_attendance_for_existing_events(self):
        EventLink = self.env["ojt.event.link"].sudo()
        Attendance = self.env["ojt.attendance"].sudo()
        for p in self:
            if not p.batch_id:
                continue
            links = EventLink.search([("batch_id", "=", p.batch_id.id)])
            if not links:
                continue

            existing = Attendance.search_read(
                domain=[("participant_id", "=", p.id), ("event_link_id", "in", links.ids)],
                fields=["event_link_id"],
                limit=0,
            )
            existing_link_ids = {e["event_link_id"][0] for e in existing if e.get("event_link_id")}

            to_create = []
            for l in links:
                if l.id in existing_link_ids:
                    continue
                to_create.append(
                    {
                        "batch_id": p.batch_id.id,
                        "event_link_id": l.id,
                        "participant_id": p.id,
                        "presence": "absent",
                        "method": "manual",  # will update on check-in
                    }
                )
            if to_create:
                Attendance.create(to_create)
