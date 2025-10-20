# -*- coding: utf-8 -*-
from odoo import http, _
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager


class OjtPortal(CustomerPortal):

    # Prepare portal layout counters (participant count for current partner)
    def _prepare_portal_layout_values(self):
        values = super()._prepare_portal_layout_values()
        partner = request.env.user.partner_id
        p_count = request.env['ojt.participant'].sudo().search_count([
            ('partner_id', '=', partner.id)
        ])
        values.update({'ojt_participant_count': p_count})
        return values

    # Portal: list participant records for current partner with pager
    @http.route(['/my/ojt'], type='http', auth='user', website=True)
    def portal_my_ojt(self, page=1, **kw):
        partner = request.env.user.partner_id
        Participant = request.env['ojt.participant'].sudo()

        domain = [('partner_id', '=', partner.id)]
        total = Participant.search_count(domain)

        p = portal_pager(url="/my/ojt", total=total, page=page, step=20)
        participants = Participant.search(domain, order="create_date desc, id desc", limit=20, offset=p['offset'])

        values = self._prepare_portal_layout_values()
        values.update({
            'participants': participants,
            'page_name': 'ojt',
            'pager': p,
        })
        return request.render('solvera_ojt_core.portal_my_ojt_dashboard', values)

    # Portal: participant detail with portal access guard and optional return URL
    @http.route(['/my/ojt/participant/<int:participant_id>'], type='http', auth='user', website=True)
    def portal_my_ojt_participant_detail(self, participant_id=None, **kw):
        user = request.env.user
        partner = user.partner_id

        Participant = request.env['ojt.participant'].sudo()
        Submission = request.env['ojt.submission'].sudo()
        Attendance = request.env['ojt.attendance'].sudo()
        Certificate = request.env['ojt.certificate'].sudo()

        # Domain: restrict to own record for portal users
        domain = [('id', '=', participant_id)]
        is_portal_user = user.has_group('base.group_portal') and not user.has_group('base.group_user')
        if is_portal_user:
            domain.append(('partner_id', '=', partner.id))

        participant = Participant.search(domain, limit=1)
        if not participant:
            return request.not_found()

        submissions = Submission.search([('participant_id', '=', participant.id)], order="create_date desc, id desc")
        attendance = Attendance.search([('participant_id', '=', participant.id)], order="id desc")
        certificates = Certificate.search([('participant_id', '=', participant.id)], order="create_date desc, id desc")

        values = self._prepare_portal_layout_values()
        values.update({
            'participant': participant,
            'submissions': submissions,
            'attendance': attendance,
            'certificates': certificates,
            'page_name': 'ojt',
            'ret': request.params.get('ret'),  # Pass-through return URL parameter
        })
        return request.render('solvera_ojt_core.portal_my_ojt_participant_detail', values)
