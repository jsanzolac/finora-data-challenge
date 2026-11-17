"""finora-dq-api entry point: the DQ routes (handler.py, unchanged), the
acquisition routes (acq.py, contracts/acq_api_contract.md v1.1) and the MRR
routes (mrr.py, contracts/mrr_api_contract.md v1). Every route
goes through authlib's dispatch and require_user (401, 403 password_change_required)."""

from __future__ import annotations

import acq
import handler as dq
import mrr
from authlib.http import dispatch

ROUTES = {**dq.ROUTES, **acq.ROUTES, **mrr.ROUTES}


def handler(event, context):
    return dispatch(ROUTES, event)
